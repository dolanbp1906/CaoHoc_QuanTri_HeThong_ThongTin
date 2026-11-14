"""Bước 6: tổng hợp bảng (CSV) và hình (PNG) cho báo cáo từ kết quả thô."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import metrics  # noqa: E402

R, F = ROOT / "results", ROOT / "figures"
F.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
INK, MUTED, GRID = "#1B1F23", "#6B7785", "#D9E2E5"
POL_LABEL = {"random": "Random", "deadline_first": "Deadline-first", "risk_first": "Risk-first",
             "cis_greedy": "CIS-greedy", "cis_knapsack_raw": "CIS (p thô)", "cis_knapsack": "CIS (Platt-val)",
             "cis_knapsack_oof": "CIS (Platt-OOF)", "cis_knapsack_testcal": "CIS (hiệu chỉnh trên test – chẩn đoán)",
             "oracle": "Oracle (biết y)"}
CAL_LABEL = {"raw": "Thô", "platt": "Platt (val 08/2016)", "isotonic": "Isotonic (val 08/2016)", "platt_oof": "Platt (OOF train)"}


def ms(s, d=3):
    return f"{s.mean():.{d}f} ± {s.std(ddof=1):.{d}f}"


def boot_ci(x, n=5000, seed=1001):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    b = rng.choice(x, size=(n, len(x)), replace=True).mean(1)
    return np.quantile(b, [0.025, 0.975])


def table_models():
    m = pd.read_csv(R / "main_tau14_metrics.csv")
    rows = []
    for (mod, cal), g in m[m.split == "test"].groupby(["model", "calib"], sort=False):
        v = m[(m.split == "valsel") & (m.model == mod) & (m.calib == cal)]
        rows.append({"Mô hình": mod.upper(), "Hiệu chỉnh": CAL_LABEL[cal], "AUC-ROC": ms(g.auc_roc), "AUC-PR": ms(g.auc_pr),
                     "F1": ms(g.f1), "Brier": ms(g.brier, 4), "ECE": ms(g.ece, 4),
                     "Brier (valsel)": f"{v.brier.mean():.4f}", "ECE (valsel)": f"{v.ece.mean():.4f}",
                     "Huấn luyện (s)": f"{g.fit_s.mean():.1f}", "Dự báo (ms/1000 dòng)": f"{g.pred_ms_per_1k.mean():.2f}"})
    t = pd.DataFrame(rows)
    t.to_csv(R / "table3_models.csv", index=False)
    return t


def table_policy():
    p = pd.read_csv(R / "policy_main_tau14.csv")
    main = p[(p.scenario == "const") & (p.budget == 0.10) & (p.effect == 0.3)]
    base = main[main.policy == "risk_first"].set_index("seed")["net_benefit"]
    rows = []
    for pol in POL_LABEL:
        g = main[main.policy == pol].set_index("seed")
        d = g["net_benefit"] - base
        lo, hi = boot_ci(d) if pol != "risk_first" else (0, 0)
        rows.append({"Chính sách": POL_LABEL[pol], "Lợi ích ròng (CU)": ms(g.net_benefit, 0),
                     "Thiệt hại tránh được (CU)": ms(g.avoided_loss, 0), "Chi phí đã dùng (CU)": ms(g.spent, 0),
                     "Số ca can thiệp": f"{g.n_selected.mean():.0f}", "Tỷ lệ trúng ca trễ": ms(g.precision, 3),
                     "Chênh lệch so với Risk-first [95% CI]": "—" if pol == "risk_first" else f"{d.mean():+.0f} [{lo:+.0f}; {hi:+.0f}]"})
    t = pd.DataFrame(rows)
    t.to_csv(R / "table3b_policy_main.csv", index=False)
    lat = pd.read_csv(R / "policy_latency_main_tau14.csv")
    return t, main["model"].iloc[0], main["p_main"].iloc[0], lat


def table_sensitivity():
    p = pd.read_csv(R / "policy_main_tau14.csv")
    keep = ["random", "deadline_first", "risk_first", "cis_knapsack", "cis_knapsack_oof", "oracle"]
    g = (p[p.policy.isin(keep)].groupby(["scenario", "budget", "effect", "policy"]).net_benefit.mean().unstack("policy")[keep]
         .round(0).reset_index())
    g.columns = [POL_LABEL.get(c, c) for c in g.columns]
    g.to_csv(R / "table4_budget_effect.csv", index=False)
    return g


def table_stress():
    out = {}
    if (R / "stress_censor.csv").exists():
        c = pd.read_csv(R / "stress_censor.csv")
        out["censor"] = c.groupby("variant").agg(rows=("n_train_rows", "mean"), train_late=("train_late_share", "mean"),
                                                 mean_p=("mean_p", "mean"), auc=("auc_roc", "mean"), brier=("brier", "mean"),
                                                 ece=("ece", "mean"), net_cis=("net_cis_knapsack", "mean"),
                                                 net_cis_sd=("net_cis_knapsack", "std")).round(4)
    if (R / "stress_missing.csv").exists():
        m = pd.read_csv(R / "stress_missing.csv")
        out["missing"] = m.groupby(["where", "missing_rate"]).agg(auc=("auc_roc", "mean"), brier=("brier", "mean"),
                                                                   ece=("ece", "mean"), net_cis=("net_cis_knapsack", "mean"),
                                                                   net_risk=("net_risk_first", "mean")).round(4)
    if (R / "stress_tau.csv").exists():
        t = pd.read_csv(R / "stress_tau.csv")
        out["tau"] = t.groupby(["tau", "p_source"]).agg(auc=("auc_roc", "mean"), brier=("brier", "mean"), ece=("ece", "mean"),
                                                         net_cis=("net_cis_knapsack", "mean"), net_risk=("net_risk_first", "mean"),
                                                         net_deadline=("net_deadline_first", "mean"), net_oracle=("net_oracle", "mean")).round(4)
    if (R / "stress_drift.csv").exists():
        d = pd.read_csv(R / "stress_drift.csv")
        out["drift"] = d.groupby(["month", "p_source"]).agg(late=("late_share", "mean"), mean_p=("mean_p", "mean"),
                                                            ece=("ece", "mean"), auc=("auc", "mean")).round(4)
    for k, v in out.items():
        v.to_csv(R / f"table4_stress_{k}.csv")
    return out


def fig_architecture():
    fig, ax = plt.subplots(figsize=(14, 3.6))
    ax.axis("off")
    boxes = [("Nhật ký XES\nBPI 2017", "#E6EFF1"), ("Chuẩn hóa +\nkiểm tra dữ liệu", "#E6EFF1"),
             ("Nhãn τ,\ncensoring,\nchia theo\nthời gian", "#E6EFF1"), ("Snapshot\ntiền tố h_i(t)\n79 đặc trưng", "#E6EFF1"),
             ("P1: LR / RF /\nXGB + hiệu\nchỉnh", "#117A8B"), ("CIS =\np·L·e − c", "#E6EFF1"),
             ("P2: Knapsack\nΣc·x ≤ B\n(HiGHS)", "#117A8B"), ("Danh sách\ncan thiệp +\nnhật ký", "#E6EFF1")]
    w, gap = 1.5, 0.3
    for i, (t, col) in enumerate(boxes):
        x = i * (w + gap)
        ax.add_patch(plt.Rectangle((x, 0.9), w, 1.1, color=col, ec="none"))
        ax.text(x + w / 2, 1.45, t, ha="center", va="center", fontsize=9, color="white" if col == "#117A8B" else INK)
        if i < len(boxes) - 1:
            ax.annotate("", xy=(x + w + gap - 0.02, 1.45), xytext=(x + w + 0.02, 1.45),
                        arrowprops=dict(arrowstyle="->", color=MUTED))
    gov = [(0, 3, "Quản trị dữ liệu: manifest.csv, sha256,\nlicense, split index"),
           (3, 5, "Quản trị mô hình: seeds 1001–1010,\nchọn trên valsel, không nhìn test"),
           (5, 8, "Quản trị quyết định: ngân sách B, giả định c/L/e\ncó đơn vị, latency p95, log")]
    for a, b, t in gov:
        x0, x1 = a * (w + gap), b * (w + gap) - gap
        ax.plot([x0, x1], [0.75, 0.75], color="#E8962E", lw=2)
        ax.text((x0 + x1) / 2, 0.38, t, ha="center", va="center", fontsize=9, color=INK)
    ax.set_xlim(-0.1, 8 * (w + gap)); ax.set_ylim(0, 2.1)
    fig.savefig(F / "fig1_architecture.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_reliability():
    pred = pd.read_parquet(ROOT / "data/processed/main_tau14_test_preds.parquet")
    g = pred[(pred.model == "xgb") & (pred.seed == 1001)]
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    ax.plot([0, 1], [0, 1], color=GRID, lw=1.5, label="Hiệu chỉnh hoàn hảo")
    for col, lab, c in (("p_raw", "Thô", "#5B7FA3"), ("p_platt", "Platt (val 08/2016)", "#C8414F"),
                        ("p_platt_oof", "Platt (OOF train)", "#117A8B")):
        t = metrics.reliability_table(g[col], g.y, 15)
        t = t[t.n >= 50]
        ax.plot(t.conf, t.acc, marker="o", ms=4, color=c,
                label=f"{lab} – ECE {metrics.ece(g[col], g.y):.3f}")
    ax.set_xlabel("Xác suất dự báo trung bình (conf)")
    ax.set_ylabel("Tỷ lệ trễ thực tế (acc)")
    ax.set_title("Reliability – XGBoost, tập test (10–12/2016), seed 1001", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.grid(color=GRID, lw=0.5)
    fig.savefig(F / "fig2_reliability.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_budget():
    p = pd.read_csv(R / "policy_main_tau14.csv")
    d = p[(p.scenario == "const") & (p.effect == 0.3)]
    pols = [("random", "#8A96A3"), ("deadline_first", "#E8962E"), ("risk_first", "#5B7FA3"),
            ("cis_knapsack", "#117A8B"), ("oracle", "#4E9A5B")]
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for pol, c in pols:
        s = d[d.policy == pol].groupby("budget").net_benefit.agg(["mean", "std"])
        ax.errorbar(s.index * 100, s["mean"], yerr=s["std"], marker="o", ms=4, color=c, capsize=3, label=POL_LABEL[pol],
                    ls="--" if pol == "oracle" else "-")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Ngân sách B (% tổng chi phí ứng viên mỗi tuần)")
    ax.set_ylabel("Lợi ích ròng trên giai đoạn test (CU)")
    ax.set_xticks([5, 10, 20])
    ax.set_title("Trade-off ngân sách – lợi ích ròng (e = 0,3; mean ± SD, 10 seeds)", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", color=GRID, lw=0.5)
    fig.savefig(F / "fig3_budget_tradeoff.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_drift():
    m = pd.read_csv(R / "monthly_late_share.csv")
    m = m[m["size"] > 3000].groupby("month").apply(lambda g: np.average(g["mean"], weights=g["size"])).rename("late")
    d = pd.read_csv(R / "stress_drift.csv")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(m.index, m.values, color=INK, marker="o", ms=4, label="Tỷ lệ snapshot trễ thực tế")
    for col, lab, c in (("p_raw", "TB xác suất – thô (gần trùng OOF)", "#5B7FA3"), ("p_platt", "TB xác suất – Platt (val)", "#C8414F"),
                        ("p_platt_oof", "TB xác suất – Platt (OOF)", "#117A8B")):
        s = d[d.p_source == col].groupby("month").mean_p.mean()
        ax.plot(s.index, s.values, ls="--", marker=".", color=c, label=lab)
    ax.axvspan(6.5, 8.5, color="#E8962E", alpha=0.12)
    ax.text(7.5, ax.get_ylim()[0] + 0.005, "valcal + valsel", ha="center", fontsize=8, color=MUTED)
    ax.set_ylabel("Tỷ lệ / xác suất")
    ax.set_title("Drift tỷ lệ trễ theo tháng (τ = 14) và mức xác suất trung bình trên test", fontsize=10)
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False, fontsize=7.5, ncol=2)
    ax.grid(axis="y", color=GRID, lw=0.5)
    fig.savefig(F / "fig4_drift.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    t3 = table_models(); print(t3.to_string(index=False))
    t3b, model, pm, lat = table_policy(); print(model, pm); print(t3b.to_string(index=False)); print(lat)
    print(table_sensitivity().to_string(index=False))
    for k, v in table_stress().items():
        print("\n==", k); print(v.to_string())
    fig_architecture(); fig_reliability(); fig_budget()
    if (R / "stress_drift.csv").exists():
        fig_drift()


if __name__ == "__main__":
    main()
