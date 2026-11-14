"""Bước 3: huấn luyện baseline (LR, RF, XGBoost) trên train, hiệu chỉnh trên valcal (08/2016),
chọn ngưỡng/bộ hiệu chỉnh trên valsel (09/2016), đánh giá trên test (10–12/2016). Không dùng test để chọn.

Chạy: python scripts/03_train.py --tau 14 --models lr,rf,xgb --seeds 1001-1010
"""
import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import data, features, metrics, models  # noqa: E402


def parse_seeds(s, cfg):
    if s is None:
        return cfg["seeds"]
    if "-" in s:
        a, b = map(int, s.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in s.split(",")]


def run(X, cfg, model_names, seeds, out_prefix, save_preds=True, train_mask=None, verbose=True):
    fcols = features.feature_columns(X)
    known = X["y"].notna()
    tr = (X["split"] == "train") & known if train_mask is None else train_mask
    vc = (X["split"] == "valcal") & known
    vs = (X["split"] == "valsel") & known
    te = (X["split"] == "test") & known
    Xtr, ytr = X.loc[tr, fcols].to_numpy(np.float32), X.loc[tr, "y"].to_numpy(int)
    rows, preds = [], []
    nb = cfg["calibration"]["ece_bins"]
    for name in model_names:
        for seed in seeds:
            t0 = time.perf_counter()
            m = models.make_model(name, cfg["models"][name], seed).fit(Xtr, ytr)
            fit_s = time.perf_counter() - t0
            t0 = time.perf_counter()
            s = {k: m.predict_proba(X.loc[mask, fcols].to_numpy(np.float32))[:, 1]
                 for k, mask in (("valcal", vc), ("valsel", vs), ("test", te))}
            pred_ms_per_1k = (time.perf_counter() - t0) / (vc.sum() + vs.sum() + te.sum()) * 1e6
            y = {k: X.loc[mask, "y"].to_numpy(int) for k, mask in (("valcal", vc), ("valsel", vs), ("test", te))}
            test_out = {}
            oof = None
            if "platt_oof" in cfg["calibration"]["methods"]:
                # Điểm out-of-fold trên TRAIN (GroupKFold theo case) để hiệu chỉnh "trong phân phối train"
                from sklearn.model_selection import GroupKFold
                oof = np.zeros(len(ytr))
                groups = X.loc[tr, "case_id"].to_numpy()
                for k, (a, b) in enumerate(GroupKFold(n_splits=5).split(Xtr, ytr, groups)):
                    mk = models.make_model(name, cfg["models"][name], seed + 100 * k).fit(Xtr[a], ytr[a])
                    oof[b] = mk.predict_proba(Xtr[b])[:, 1]
            for cal in cfg["calibration"]["methods"]:
                if cal == "platt_oof":
                    c = models.Calibrator("platt").fit(oof, ytr)
                else:
                    c = models.Calibrator(cal).fit(s["valcal"], y["valcal"])
                p_vs, p_te = c.predict(s["valsel"]), c.predict(s["test"])
                th = metrics.best_f1_threshold(p_vs, y["valsel"])          # ngưỡng chọn trên validation
                for sp, p in (("valsel", p_vs), ("test", p_te)):
                    r = metrics.classification_metrics(p, y[sp], th, nb)
                    r.update(model=name, calib=cal, seed=seed, split=sp, fit_s=round(fit_s, 2),
                             pred_ms_per_1k=round(pred_ms_per_1k, 3))
                    rows.append(r)
                test_out[f"p_{cal}"] = p_te.astype(np.float32)
            if save_preds:
                d = X.loc[te, ["case_id", "t", "y", "delta_days", "requested_amount", "cnt_O_Create_Offer"]].copy()
                d["model"], d["seed"] = name, seed
                for k, v in test_out.items():
                    d[k] = v
                preds.append(d)
            if verbose:
                last = [r for r in rows if r["model"] == name and r["seed"] == seed and r["split"] == "test"]
                print(f"{name} seed={seed} fit={fit_s:.1f}s | " +
                      " ".join(f"{r['calib']}: AUC={r['auc_roc']:.3f} Brier={r['brier']:.4f} ECE={r['ece']:.4f}" for r in last),
                      flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "results" / f"{out_prefix}_metrics.csv", index=False)
    if save_preds:
        pd.concat(preds).to_parquet(ROOT / "data" / "processed" / f"{out_prefix}_test_preds.parquet", index=False)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--tau", type=int, default=14)
    ap.add_argument("--models", default="lr,rf,xgb")
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    cfg = data.load_config(args.config)
    X = pd.read_parquet(ROOT / "data" / "processed" / f"snap_tau{args.tau}.parquet")
    seeds = parse_seeds(args.seeds, cfg)
    t0 = time.perf_counter()
    res = run(X, cfg, args.models.split(","), seeds, f"{args.tag}_tau{args.tau}")
    env = {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor(),
           "runtime_s": round(time.perf_counter() - t0, 1)}
    import sklearn, xgboost, scipy  # noqa: E401
    env.update(sklearn=sklearn.__version__, xgboost=xgboost.__version__, scipy=scipy.__version__,
               pandas=pd.__version__, numpy=np.__version__)
    (ROOT / "results" / f"env_{args.tag}_tau{args.tau}.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    summ = (res[res.split == "test"].groupby(["model", "calib"])[["auc_roc", "auc_pr", "f1", "brier", "ece"]]
            .agg(["mean", "std"]).round(4))
    print(summ.to_string())


if __name__ == "__main__":
    main()
