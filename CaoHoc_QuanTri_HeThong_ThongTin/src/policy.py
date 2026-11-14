"""Chính sách chọn hồ sơ can thiệp dưới ngân sách B.

score_i = p_i · L_i · e_i − c_i   (Calibrated Intervention Score – CIS)
max Σ score_i·x_i  s.t.  Σ c_i·x_i ≤ B,  x ∈ {0,1}^N        (0/1 knapsack)
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


def cis_score(p, L, e, c):
    return np.asarray(p, float) * np.asarray(L, float) * np.asarray(e, float) - np.asarray(c, float)


def greedy_fill(order, c, budget: float) -> np.ndarray:
    """Duyệt theo thứ tự ưu tiên, nhận hồ sơ nếu còn đủ ngân sách."""
    x = np.zeros(len(c), dtype=bool)
    left = float(budget)
    for i in order:
        if c[i] <= left + 1e-9:
            x[i] = True
            left -= c[i]
    return x


def knapsack_milp(value, c, budget: float) -> np.ndarray:
    """Lời giải chính xác 0/1 knapsack bằng HiGHS (scipy.optimize.milp). Chỉ xét value > 0."""
    value, c = np.asarray(value, float), np.asarray(c, float)
    x = np.zeros(len(value), dtype=bool)
    pos = np.where(value > 1e-12)[0]
    if len(pos) == 0 or budget <= 0:
        return x
    if c[pos].sum() <= budget:  # đủ ngân sách cho mọi hồ sơ có lợi
        x[pos] = True
        return x
    res = milp(c=-value[pos], constraints=LinearConstraint(c[pos][None, :], -np.inf, budget),
               integrality=np.ones(len(pos)), bounds=Bounds(0, 1),
               options={"time_limit": 60, "mip_rel_gap": 1e-6})
    if res.x is None:  # hết giờ mà chưa có nghiệm khả thi → dùng greedy theo tỷ số, ghi nhận lại
        MILP_FALLBACKS.append(res.message)
        order = pos[np.argsort(-(value[pos] / c[pos]), kind="stable")]
        return greedy_fill(order, c, budget)
    x[pos] = res.x > 0.5
    return x


MILP_FALLBACKS: list = []


def knapsack_dp(value, c, budget: int) -> tuple[np.ndarray, float]:
    """Quy hoạch động O(N·B) cho chi phí nguyên – dùng để kiểm chứng MILP trong unit test."""
    value, c = np.asarray(value, float), np.asarray(c, int)
    n, B = len(value), int(budget)
    best = np.zeros((n + 1, B + 1))
    for i in range(1, n + 1):
        best[i] = best[i - 1]
        if c[i - 1] <= B:
            cand = best[i - 1, : B + 1 - c[i - 1]] + value[i - 1]
            best[i, c[i - 1]:] = np.maximum(best[i - 1, c[i - 1]:], cand)
    x = np.zeros(n, dtype=bool)
    b = B
    for i in range(n, 0, -1):
        if best[i, b] != best[i - 1, b]:
            x[i - 1] = True
            b -= c[i - 1]
    return x, float(best[n, B])


def select(policy: str, cand, budget: float, rng: np.random.Generator) -> np.ndarray:
    """cand: dict/DataFrame với p_cal, p_raw, delta, c, L, e, y (y chỉ dùng cho oracle)."""
    c = np.asarray(cand["c"], float)
    n = len(c)
    if policy == "random":
        return greedy_fill(rng.permutation(n), c, budget)
    if policy == "deadline_first":
        return greedy_fill(np.argsort(np.asarray(cand["delta"]), kind="stable"), c, budget)
    if policy == "risk_first":
        return greedy_fill(np.argsort(-np.asarray(cand["p_cal"]), kind="stable"), c, budget)
    if policy == "cis_knapsack":
        return knapsack_milp(cis_score(cand["p_cal"], cand["L"], cand["e"], c), c, budget)
    if policy == "cis_knapsack_raw":   # ablation: bỏ bước hiệu chỉnh
        return knapsack_milp(cis_score(cand["p_raw"], cand["L"], cand["e"], c), c, budget)
    if policy == "cis_greedy":         # ablation: greedy theo tỷ số thay cho lời giải chính xác
        v = cis_score(cand["p_cal"], cand["L"], cand["e"], c)
        order = [i for i in np.argsort(-(v / c), kind="stable") if v[i] > 0]
        return greedy_fill(order, c, budget)
    if policy == "oracle":             # cận trên: biết trước y (không khả thi thực tế)
        return knapsack_milp(cis_score(cand["y"], cand["L"], cand["e"], c), c, budget)
    raise ValueError(policy)


def evaluate_selection(x, cand) -> dict:
    """Lợi ích thực hiện (theo nhãn thật) dưới giả định hiệu quả e: tránh được y·L·e, tốn c."""
    x = np.asarray(x, bool)
    y, L, e, c = (np.asarray(cand[k], float) for k in ("y", "L", "e", "c"))
    avoided = float((x * y * L * e).sum())
    spent = float((x * c).sum())
    return {"n_selected": int(x.sum()), "hits": int((x * y).sum()), "avoided_loss": avoided,
            "spent": spent, "net_benefit": avoided - spent,
            "potential_loss": float((y * L * e).sum())}
