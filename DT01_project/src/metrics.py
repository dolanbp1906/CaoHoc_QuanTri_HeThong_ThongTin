"""Chỉ số phân lớp và hiệu chỉnh: AUC-ROC, AUC-PR, F1, Brier, ECE, reliability; bootstrap theo case."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score


def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def reliability_table(p, y, n_bins: int = 15) -> pd.DataFrame:
    """Bin đều trên [0,1]; acc = tỷ lệ trễ thực, conf = xác suất trung bình."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, n_bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)
    rows = []
    for k in range(n_bins):
        m = b == k
        if m.any():
            rows.append({"bin": k, "lo": edges[k], "hi": edges[k + 1], "n": int(m.sum()),
                         "conf": float(p[m].mean()), "acc": float(y[m].mean())})
    return pd.DataFrame(rows)


def ece(p, y, n_bins: int = 15) -> float:
    t = reliability_table(p, y, n_bins)
    if t.empty:
        return float("nan")
    return float((t["n"] / t["n"].sum() * (t["acc"] - t["conf"]).abs()).sum())


def best_f1_threshold(p, y) -> float:
    grid = np.linspace(0.05, 0.95, 91)
    scores = [f1_score(y, (np.asarray(p) >= th).astype(int), zero_division=0) for th in grid]
    return float(grid[int(np.argmax(scores))])


def classification_metrics(p, y, threshold: float, n_bins: int = 15) -> dict:
    y = np.asarray(y, int)
    return {
        "auc_roc": float(roc_auc_score(y, p)),
        "auc_pr": float(average_precision_score(y, p)),
        "f1": float(f1_score(y, (np.asarray(p) >= threshold).astype(int), zero_division=0)),
        "brier": brier(p, y),
        "ece": ece(p, y, n_bins),
        "threshold": float(threshold),
        "n": int(len(y)),
    }


def bootstrap_ci(df: pd.DataFrame, stat_fn, group_col: str = "case_id", n_boot: int = 500, seed: int = 1001,
                 alpha: float = 0.05) -> tuple[float, float]:
    """CI bootstrap lấy mẫu lại theo hồ sơ (đơn vị độc lập), không theo dòng snapshot."""
    rng = np.random.default_rng(seed)
    groups = df[group_col].unique()
    idx = df.groupby(group_col).indices
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(groups, size=len(groups), replace=True)
        rows = np.concatenate([idx[g] for g in pick])
        vals.append(stat_fn(df.iloc[rows]))
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
