"""Bước 5 (RQ3 + độ nhạy): censoring, mất sự kiện, τ khác nhau, drift theo tháng. Mô hình: XGBoost.

Chạy: python scripts/05_stress.py --parts censor,missing,tau,drift
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import data, features, metrics, models  # noqa: E402

def _load_script(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def policy_main(pred, cfg, tau, p_col="p_raw"):
    """Lợi ích ròng của CIS-knapsack và risk-first ở thiết lập chính (B=10%, e=0.3, const)."""
    sim = _load_script("04_calibrate_policy")
    pred = pred.copy()
    pred["p_platt"] = pred[p_col]
    for col in ("p_platt_oof", "p_testcal"):
        if col not in pred:
            pred[col] = pred[p_col]
    res = sim.simulate(pred, cfg, cfg["policy"]["main_budget"], cfg["policy"]["main_effect"], "const",
                       int(pred["seed"].iloc[0]), tau, "p_platt",
                       policies=["random", "deadline_first", "risk_first", "cis_knapsack", "oracle"])
    return {f"net_{k}": res[k]["net_benefit"] for k in ("cis_knapsack", "risk_first", "deadline_first", "random", "oracle")}


def fit_predict(Xtr, ytr, Xte, cfg, seed):
    m = models.make_model("xgb", cfg["models"]["xgb"], seed).fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def part_censor(cfg, seeds, out):
    """Dữ liệu train được 'trích xuất' tại cutoff: hồ sơ còn mở bị censored. So sánh 3 cách gán nhãn."""
    X = pd.read_parquet(ROOT / "data/processed/snap_tau14.parquet")
    fcols = features.feature_columns(X)
    te = X[(X.split == "test") & X.y.notna()]
    ev = data.load_events(cfg)
    cut = cfg["stress"]["censor_cutoff"]
    ev_cut = ev[ev["timestamp"] <= pd.Timestamp(cut, tz="UTC")]
    cases = data.build_cases(ev_cut, cfg, 14, extraction_time=cut + "T00:00Z")
    cases["split"] = "train"
    fs = features.FeatureSpace.fit(ev_cut, cases)
    snap = features.make_snapshots(cases, 14)
    Xc = features.snapshot_features(snap, features.event_level_cumulative(ev_cut, fs), cases, fs, 14)
    Xc = Xc.reindex(columns=list(Xc.columns) + [c for c in fcols if c not in Xc.columns], fill_value=0)
    status = cases["label_status"].reindex(Xc["case_id"]).to_numpy()
    variants = {
        "naive_zero": (np.ones(len(Xc), bool), np.where(status == "observed", Xc["y"], 0.0)),
        "drop_all_open": (status == "observed", Xc["y"].to_numpy()),
        "correct": (status != "censored_unknown", Xc["y"].to_numpy()),
    }
    cs = cases["label_status"].value_counts().to_dict()
    print("censor cutoff label status:", cs)
    rows = []
    for v, (mask, y) in variants.items():
        for seed in seeds:
            p = fit_predict(Xc.loc[mask, fcols].to_numpy(np.float32), np.asarray(y)[mask].astype(int),
                            te[fcols].to_numpy(np.float32), cfg, seed)
            r = metrics.classification_metrics(p, te["y"].astype(int), 0.5)
            pred = te[["case_id", "t", "y", "delta_days", "requested_amount", "cnt_O_Create_Offer"]].assign(p_raw=p, seed=seed)
            r.update(policy_main(pred, cfg, 14))
            r.update(variant=v, seed=seed, n_train_rows=int(mask.sum()), mean_p=float(p.mean()),
                     train_late_share=float(np.asarray(y)[mask].mean()), **{f"status_{k}": n for k, n in cs.items()})
            rows.append(r)
        print("censor", v, "done", flush=True)
    pd.DataFrame(rows).to_csv(out / "stress_censor.csv", index=False)


def part_missing(cfg, seeds, out):
    """Mất 0/10/30% sự kiện: (a) chỉ ở test – log triển khai kém; (b) ở mọi tập."""
    ev = data.load_events(cfg)
    cases = data.build_cases(ev, cfg, 14)
    cases["split"] = data.assign_split(cases, cfg)
    tr_ids = cases.index[cases.split == "train"]
    fs = features.FeatureSpace.fit(ev[ev.case_id.isin(tr_ids)], cases.loc[tr_ids])
    snap = features.make_snapshots(cases, 14)
    clean = features.snapshot_features(snap, features.event_level_cumulative(ev, fs), cases, fs, 14)
    fcols = features.feature_columns(clean)
    rows = []
    for rate in cfg["stress"]["missing_rates"]:
        for seed in seeds:
            noisy = clean if rate == 0 else features.snapshot_features(
                snap, features.event_level_cumulative(features.drop_events(ev, rate, seed), fs), cases, fs, 14)
            for where in ("test_only", "all"):
                trX = clean if where == "test_only" else noisy
                tr = trX[(trX.split == "train") & trX.y.notna()]
                te = noisy[(noisy.split == "test") & noisy.y.notna()]
                p = fit_predict(tr[fcols].to_numpy(np.float32), tr.y.astype(int), te[fcols].to_numpy(np.float32), cfg, seed)
                r = metrics.classification_metrics(p, te.y.astype(int), 0.5)
                pred = te[["case_id", "t", "y", "delta_days", "requested_amount", "cnt_O_Create_Offer"]].assign(p_raw=p, seed=seed)
                r.update(policy_main(pred, cfg, 14))
                r.update(missing_rate=rate, where=where, seed=seed)
                rows.append(r)
        print("missing", rate, "done", flush=True)
    pd.DataFrame(rows).to_csv(out / "stress_missing.csv", index=False)


def part_tau(cfg, seeds, out):
    tr_mod = _load_script("03_train")
    rows = []
    for tau in cfg["label"]["tau_sensitivity"]:
        X = pd.read_parquet(ROOT / f"data/processed/snap_tau{tau}.parquet")
        res = tr_mod.run(X, cfg, ["xgb"], seeds, f"tau_tau{tau}", save_preds=True, verbose=False)
        pred = pd.read_parquet(ROOT / f"data/processed/tau_tau{tau}_test_preds.parquet")
        for seed in seeds:
            for pcol in ("p_raw", "p_platt", "p_platt_oof"):
                r = policy_main(pred[pred.seed == seed], cfg, tau, pcol)
                m = res[(res.split == "test") & (res.seed == seed) & (res.calib == pcol[2:])].iloc[0].to_dict()
                rows.append({**m, **r, "tau": tau, "p_source": pcol})
        print("tau", tau, "done", flush=True)
    pd.DataFrame(rows).to_csv(out / "stress_tau.csv", index=False)


def part_drift(cfg, out):
    pred = pd.read_parquet(ROOT / "data/processed/main_tau14_test_preds.parquet")
    pred = pred[pred.model == "xgb"]
    pred["month"] = pred["t"].dt.strftime("%Y-%m")
    rows = []
    for (month, seed), g in pred.groupby(["month", "seed"]):
        for pcol in ("p_raw", "p_platt", "p_isotonic", "p_platt_oof"):
            rows.append({"month": month, "seed": seed, "p_source": pcol, "n": len(g), "late_share": g.y.mean(),
                         "mean_p": g[pcol].mean(), "ece": metrics.ece(g[pcol], g.y), "brier": metrics.brier(g[pcol], g.y),
                         "auc": metrics.classification_metrics(g[pcol], g.y.astype(int), 0.5)["auc_roc"]})
    X = pd.read_parquet(ROOT / "data/processed/snap_tau14.parquet", columns=["t", "y", "split"])
    X["month"] = X["t"].dt.strftime("%Y-%m")
    X.groupby(["month", "split"]).y.agg(["mean", "size"]).reset_index().to_csv(out / "monthly_late_share.csv", index=False)
    pd.DataFrame(rows).to_csv(out / "stress_drift.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--parts", default="drift,censor,missing,tau")
    ap.add_argument("--seeds", default=None)
    args = ap.parse_args()
    cfg = data.load_config(args.config)
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else cfg["seeds"]
    out = ROOT / "results"
    parts = args.parts.split(",")
    if "drift" in parts:
        part_drift(cfg, out)
    if "censor" in parts:
        part_censor(cfg, seeds, out)
    if "missing" in parts:
        part_missing(cfg, seeds[:3], out)   # 3 seeds: mỗi seed dựng lại đặc trưng (tốn thời gian)
    if "tau" in parts:
        part_tau(cfg, seeds, out)
    from src import policy as _p
    print("MILP fallbacks:", len(_p.MILP_FALLBACKS), flush=True)


if __name__ == "__main__":
    main()
