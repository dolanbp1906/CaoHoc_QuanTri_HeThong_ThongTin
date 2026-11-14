"""Bước 4: mô phỏng chính sách can thiệp theo ngân sách trên giai đoạn test (paired-budget).

Mỗi thứ Hai 00:00 UTC (epoch), ứng viên = hồ sơ test đang mở, chưa quá hạn, chưa được can thiệp.
B = β · Σ c_i của ứng viên. Hiệu quả e là GIẢ ĐỊNH: can thiệp loại bỏ tỷ lệ e rủi ro trễ.
Lợi ích thực hiện đo bằng nhãn thật: Σ x_i (y_i L_i e_i − c_i)  →  chỉ là tối ưu TRONG MÔ PHỎNG.

Chạy: python scripts/04_calibrate_policy.py --budgets 0.05,0.10,0.20
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import data, features, models, policy  # noqa: E402

POLICIES = ["random", "deadline_first", "risk_first", "cis_greedy", "cis_knapsack_raw", "cis_knapsack",
            "cis_knapsack_oof", "cis_knapsack_testcal", "oracle"]


def effect_vector(e, delta, tau, scenario):
    if scenario == "decay":   # can thiệp càng sát hạn càng kém tác dụng: e·min(1, Δ/(τ/2))
        return e * np.clip(delta / (tau / 2.0), 0, 1)
    return np.full(len(delta), e)


def simulate(pred, cfg, budget_frac, e, scenario, seed, tau, p_main="p_platt", homog=False, timing=None,
             policies=None):
    policies = policies or POLICIES
    rng = np.random.default_rng(seed)
    ep = pred[pred["t"].dt.dayofweek == 0].sort_values("t")
    c_all, L_all = features.cost_and_loss(ep, cfg["policy"])
    if homog:  # độ nhạy: chi phí/thiệt hại đồng nhất
        c_all, L_all = np.ones(len(ep)), np.full(len(ep), 10.0)
    ep = ep.assign(c=c_all, L=L_all)
    out = {pol: {"n_selected": 0, "hits": 0, "avoided_loss": 0.0, "spent": 0.0, "net_benefit": 0.0,
                 "potential_loss": 0.0, "budget_cu": 0.0} for pol in policies}
    done = {pol: set() for pol in policies}
    for t, g in ep.groupby("t", sort=True):
        for pol in policies:
            gg = g[~g["case_id"].isin(done[pol])]
            if gg.empty:
                continue
            cand = {"c": gg["c"].to_numpy(), "L": gg["L"].to_numpy(), "y": gg["y"].to_numpy(float),
                    "delta": gg["delta_days"].to_numpy(), "p_raw": gg["p_raw"].to_numpy(float),
                    "p_cal": gg[p_main].to_numpy(float)}
            cand["e"] = effect_vector(e, cand["delta"], tau, scenario)
            B = budget_frac * cand["c"].sum()
            name = pol
            if pol == "cis_knapsack_oof":
                cand["p_cal"], name = gg["p_platt_oof"].to_numpy(float), "cis_knapsack"
            elif pol == "cis_knapsack_testcal":
                cand["p_cal"], name = gg["p_testcal"].to_numpy(float), "cis_knapsack"
            t0 = time.perf_counter()
            x = policy.select(name, cand, B, rng)
            if timing is not None and pol == "cis_knapsack":
                timing.append((time.perf_counter() - t0) * 1000)
            r = policy.evaluate_selection(x, cand)
            for k in ("n_selected", "hits", "avoided_loss", "spent", "net_benefit", "potential_loss"):
                out[pol][k] += r[k]
            out[pol]["budget_cu"] += B
            done[pol].update(gg["case_id"].to_numpy()[x])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--tau", type=int, default=14)
    ap.add_argument("--model", default=None, help="mặc định: chọn trên valsel theo Brier")
    ap.add_argument("--budgets", default=None)
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    cfg = data.load_config(args.config)
    met = pd.read_csv(ROOT / "results" / f"{args.tag}_tau{args.tau}_metrics.csv")
    vs = met[(met.split == "valsel")].groupby(["model", "calib"])["brier"].mean()
    best_model, best_cal = vs.idxmin() if args.model is None else (args.model, None)
    if best_cal is None:
        best_cal = vs.loc[best_model].idxmin()
    print(f"Chọn trên valsel (Brier): model={best_model}, calib={best_cal}")
    pred = pd.read_parquet(ROOT / "data" / "processed" / f"{args.tag}_tau{args.tau}_test_preds.parquet")
    pred = pred[pred["model"] == best_model].copy()
    p_main = f"p_{best_cal}"
    # Chẩn đoán (KHÔNG dùng để chọn): isotonic fit trên chính tập test – trần của hiệu chỉnh khi biết drift
    pred["p_testcal"] = np.nan
    for s, g in pred.groupby("seed"):
        pred.loc[g.index, "p_testcal"] = models.Calibrator("isotonic").fit(g["p_raw"], g["y"]).predict(g["p_raw"])
    budgets = [float(b) for b in args.budgets.split(",")] if args.budgets else cfg["policy"]["budgets"]
    rows, timing = [], []
    grid = [(sc, b, e, False) for sc in ("const", "decay") for b in budgets for e in cfg["policy"]["effects"]]
    grid.append(("homog", cfg["policy"]["main_budget"], cfg["policy"]["main_effect"], True))
    for sc, b, e, homog in grid:
        for seed in cfg["seeds"]:
            g = pred[pred["seed"] == seed]
            res = simulate(g, cfg, b, e, "const" if homog else sc, seed, args.tau, p_main, homog,
                           timing if (sc == "const" and b == cfg["policy"]["main_budget"]) else None)
            for pol, r in res.items():
                rows.append({"scenario": sc, "budget": b, "effect": e, "seed": seed, "policy": pol, **r})
        print(f"done scenario={sc} budget={b} e={e}", flush=True)
    df = pd.DataFrame(rows)
    df["precision"] = df["hits"] / df["n_selected"].replace(0, np.nan)
    df["model"], df["p_main"] = best_model, p_main
    df.to_csv(ROOT / "results" / f"policy_{args.tag}_tau{args.tau}.csv", index=False)
    tm = np.array(timing)
    print("MILP fallbacks:", len(policy.MILP_FALLBACKS))
    pd.DataFrame([{"decision_ms_p50": np.percentile(tm, 50), "decision_ms_p95": np.percentile(tm, 95),
                   "decision_ms_max": tm.max(), "n_decisions": len(tm)}]).round(3).to_csv(
        ROOT / "results" / f"policy_latency_{args.tag}_tau{args.tau}.csv", index=False)
    main = df[(df.scenario == "const") & (df.budget == cfg["policy"]["main_budget"]) & (df.effect == cfg["policy"]["main_effect"])]
    print(main.groupby("policy")[["net_benefit", "avoided_loss", "spent", "n_selected", "precision"]]
          .agg(["mean", "std"]).round(1).to_string())


if __name__ == "__main__":
    main()
