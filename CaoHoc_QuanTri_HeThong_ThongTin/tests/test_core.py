"""Unit test tái hiện các ví dụ tính tay trong tài liệu phát biểu bài toán (mục 3 và mục 5)."""
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import data, features, metrics, policy  # noqa: E402

CFG = data.load_config()


# ---------- Mục 5: ví dụ A/B/C ----------
TOY = {"id": ["A", "B", "C"], "p": [0.80, 0.55, 0.40], "L": [10, 8, 15], "c": [2, 1, 3], "delta": [2, 5, 1]}


def test_toy_scores():
    s = policy.cis_score(TOY["p"], TOY["L"], 1.0, TOY["c"])
    assert np.allclose(s, [6.0, 3.4, 3.0])


def test_toy_knapsack_budget_3():
    v = policy.cis_score(TOY["p"], TOY["L"], 1.0, TOY["c"])
    x = policy.knapsack_milp(v, np.array(TOY["c"], float), 3)
    assert {TOY["id"][i] for i in np.where(x)[0]} == {"A", "B"}
    assert v[x].sum() == pytest.approx(9.4)


def test_toy_budget_one_case_picks_A():
    v = policy.cis_score(TOY["p"], TOY["L"], 1.0, TOY["c"])
    assert TOY["id"][int(np.argmax(v))] == "A"


def test_deadline_first_picks_C():
    cand = {"c": np.array(TOY["c"], float), "delta": np.array(TOY["delta"], float)}
    x = policy.select("deadline_first", cand, 3, np.random.default_rng(0))
    assert x.tolist() == [False, False, True]


def test_counterexample_risk_first():
    # D: p=0.9, L=2, c=1 ⇒ score 0.8; ngân sách 1: risk-first chọn D, CIS chọn B
    cand = {"p_cal": np.array([0.55, 0.9]), "L": np.array([8., 2.]), "c": np.array([1., 1.]), "e": 1.0}
    rng = np.random.default_rng(0)
    assert policy.select("risk_first", cand, 1, rng).tolist() == [False, True]
    assert policy.select("cis_knapsack", cand, 1, rng).tolist() == [True, False]


def test_counterexample_greedy_ratio():
    v, c = np.array([3.5, 6.0]), np.array([1.0, 3.0])
    x = policy.knapsack_milp(v, c, 3)
    assert x.tolist() == [False, True]
    order = np.argsort(-(v / c))
    assert policy.greedy_fill(order, c, 3).tolist() == [True, False]


@pytest.mark.parametrize("seed", range(20))
def test_milp_matches_dp(seed):
    rng = np.random.default_rng(seed)
    n = 25
    v = rng.normal(1, 2, n)
    c = rng.integers(1, 4, n)
    B = int(c.sum() * 0.3)
    x_m = policy.knapsack_milp(v, c.astype(float), B)
    _, best = policy.knapsack_dp(np.maximum(v, 0), c, B)
    assert (c[x_m].sum() <= B) and v[x_m].sum() == pytest.approx(best, abs=1e-6)


# ---------- Mục 3: Brier, ECE, AUC ----------
def test_brier_example():
    assert metrics.brier([0.9, 0.8, 0.7, 0.3, 0.2], [1, 1, 0, 0, 0]) == pytest.approx(0.134)


def test_ece_example():
    p = [0.8] * 6 + [0.2] * 4
    y = [1, 1, 1, 0, 0, 0] + [1, 0, 0, 0]
    assert metrics.ece(p, y, n_bins=10) == pytest.approx(0.20)


def test_auc_equal_brier_different():
    from sklearn.metrics import roc_auc_score
    y = [1, 1, 0, 0, 0]
    m1, m2 = [0.9, 0.8, 0.7, 0.3, 0.2], [0.99, 0.98, 0.97, 0.5, 0.4]
    assert roc_auc_score(y, m1) == roc_auc_score(y, m2) == 1.0
    assert metrics.brier(m2, y) == pytest.approx(0.27028)


# ---------- Mục 3: nhật ký mẫu L0, censoring, không nhìn tương lai ----------
def _toy_log():
    T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731
    rows = [
        ("A1", "A_Create Application", T("2016-01-01 09:00"), "User_1"),
        ("A1", "A_Submitted", T("2016-01-01 09:05"), "User_1"),
        ("A1", "W_Complete application", T("2016-01-02 10:00"), "User_5"),
        ("A1", "O_Create Offer", T("2016-01-05 11:00"), "User_5"),
        ("A1", "W_Validate application", T("2016-01-12 09:00"), "User_8"),
        ("A1", "A_Pending", T("2016-01-18 16:00"), "User_8"),
        ("A2", "A_Create Application", T("2016-01-02 08:00"), "User_2"),
        ("A2", "O_Create Offer", T("2016-01-04 15:00"), "User_5"),
        ("A2", "A_Pending", T("2016-01-10 08:00"), "User_8"),
        ("A3", "A_Create Application", T("2016-01-20 10:00"), "User_1"),
        ("A3", "W_Complete application", T("2016-01-22 09:00"), "User_5"),
    ]
    ev = pd.DataFrame(rows, columns=["case_id", "activity", "timestamp", "resource"])
    ev["lifecycle"] = "complete"
    ev["loan_goal"], ev["app_type"], ev["requested_amount"] = "Car", "New credit", 20000.0
    ev["file_order"] = range(len(ev))
    return ev


def test_labels_and_censoring():
    ev = _toy_log()
    cases = data.build_cases(ev, CFG, 14, extraction_time="2016-01-31T00:00Z")
    assert cases.loc["A1", "T_days"] == pytest.approx(17 + 7 / 24)
    assert cases.loc["A1", "y"] == 1 and cases.loc["A2", "y"] == 0
    assert np.isnan(cases.loc["A3", "y"]) and cases.loc["A3", "label_status"] == "censored_unknown"
    later = data.build_cases(ev, CFG, 14, extraction_time="2016-02-10T00:00Z")
    assert later.loc["A3", "y"] == 1 and later.loc["A3", "label_status"] == "censored_known_late"


def test_prefix_has_no_future_events():
    ev = _toy_log()
    cases = data.build_cases(ev, CFG, 14, extraction_time="2016-01-31T00:00Z")
    cases["split"] = "train"
    fs = features.FeatureSpace.fit(ev, cases)
    snap = features.make_snapshots(cases, 14)
    X = features.snapshot_features(snap, features.event_level_cumulative(ev, fs), cases, fs, 14)
    a1 = X[X.case_id == "A1"].set_index("t")
    row = a1.loc[pd.Timestamp("2016-01-06", tz="UTC")]
    assert row["n_events"] == 4                      # h_A1(06/01) = 4 sự kiện
    assert row["cnt_W_Validate_application"] == 0    # 12/01 là tương lai
    assert row["elapsed_days"] == pytest.approx(4 + 15 / 24)
    assert X["t"].max() < cases["deadline"].max()
    # mọi snapshot đều trước kết quả và trước hạn
    m = X.merge(cases[["t_end", "deadline"]], left_on="case_id", right_index=True)
    assert ((m["t_end"].isna()) | (m["t"] < m["t_end"])).all() and (m["t"] < m["deadline"]).all()
