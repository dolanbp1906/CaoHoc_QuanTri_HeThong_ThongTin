"""Đặc trưng tiền tố h_i(t): chỉ dùng sự kiện có timestamp ≤ t (ràng buộc C1 – không nhìn tương lai)."""
from __future__ import annotations

import numpy as np
import pandas as pd

DAY = pd.Timedelta(days=1)
LIFECYCLES = ["complete", "suspend", "schedule", "start", "resume", "ate_abort", "withdraw"]


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(s)).strip("_")


class FeatureSpace:
    """Cố định danh mục hoạt động/mục tiêu vay từ tập TRAIN để dùng lại cho val/test (fit chỉ trên train)."""

    def __init__(self, activities, loan_goals):
        self.activities = sorted(map(str, activities))
        self.loan_goals = sorted(map(str, loan_goals))

    @classmethod
    def fit(cls, events_train: pd.DataFrame, cases_train: pd.DataFrame) -> "FeatureSpace":
        return cls(events_train["activity"].unique(), cases_train["loan_goal"].dropna().unique())


def event_level_cumulative(events: pd.DataFrame, fs: FeatureSpace) -> pd.DataFrame:
    """Với mỗi sự kiện: trạng thái tích lũy của tiền tố kết thúc tại sự kiện đó."""
    ev = events[["case_id", "activity", "timestamp", "resource", "lifecycle"]].copy().reset_index(drop=True)
    g = ev.groupby("case_id", sort=False)
    out = pd.DataFrame({"case_id": ev["case_id"], "ev_time": ev["timestamp"]})  # giữ tz UTC
    out["n_events"] = g.cumcount().values + 1
    first_res = ~ev.duplicated(["case_id", "resource"])
    out["n_resources"] = first_res.groupby(ev["case_id"]).cumsum().values
    act = ev["activity"].astype(str)
    for a in fs.activities:
        out[f"cnt_{_slug(a)}"] = (act == a).astype(np.int16).groupby(ev["case_id"]).cumsum().values
    lc = ev["lifecycle"].astype(str)
    for l in LIFECYCLES:
        out[f"lc_{l}"] = (lc == l).astype(np.int16).groupby(ev["case_id"]).cumsum().values
    out["last_act"] = act.values
    return out


def make_snapshots(cases: pd.DataFrame, tau_days: float, hour_utc: int = 0) -> pd.DataFrame:
    """Mỗi ngày lúc hour_utc, mọi hồ sơ đang mở (start < t < t_end) và chưa quá hạn (t < start + τ)."""
    tau = pd.to_timedelta(float(tau_days), unit="D")
    ext = cases["extraction"]
    end = cases["t_end"].where(cases["t_end"].notna(), ext)
    upper = pd.concat([end, cases["start"] + tau, ext], axis=1).min(axis=1)
    first = (cases["start"].dt.floor("D") + pd.Timedelta(hours=hour_utc))
    first = first.where(first > cases["start"], first + DAY)
    n = np.ceil(((upper - first) / DAY).clip(lower=0)).astype(int)  # số mốc t với first + k·DAY < upper
    n = np.where(first < upper, n, 0)
    idx = np.repeat(np.arange(len(cases)), n)
    k = np.concatenate([np.arange(m) for m in n]) if len(idx) else np.array([], dtype=int)
    t_naive = first.values[idx] + k * np.timedelta64(1, "D")   # numpy datetime64 (UTC, không tz)
    keep = t_naive < upper.values[idx]
    snap = pd.DataFrame({
        "case_id": cases.index.values[idx][keep],
        "t": pd.to_datetime(t_naive[keep], utc=True),
    })
    return snap


def snapshot_features(snap: pd.DataFrame, evcum: pd.DataFrame, cases: pd.DataFrame, fs: FeatureSpace,
                      tau_days: float) -> pd.DataFrame:
    """Ghép trạng thái của sự kiện cuối cùng ≤ t (merge_asof, direction=backward)."""
    s = snap.sort_values("t").reset_index(drop=True)
    e = evcum.sort_values("ev_time")
    m = pd.merge_asof(s, e, left_on="t", right_on="ev_time", by="case_id", direction="backward", allow_exact_matches=True)
    assert m["ev_time"].notna().all(), "Snapshot không có sự kiện nào trước t"
    assert (m["ev_time"] <= m["t"]).all(), "Rò rỉ: dùng sự kiện sau thời điểm dự báo"
    c = cases.loc[m["case_id"]].reset_index(drop=True)   # căn chỉnh theo dòng của m, giữ tz
    m["elapsed_days"] = (m["t"] - c["start"]) / DAY
    m["delta_days"] = float(tau_days) - m["elapsed_days"]
    m["since_last_days"] = (m["t"] - m["ev_time"]) / DAY
    amt = c["requested_amount"].fillna(0).values.astype(float)
    m["requested_amount"] = amt
    m["log_amount"] = np.log1p(amt)
    m["limit_raise"] = (c["app_type"].astype(str).values == "Limit raise").astype(np.int8)
    goal = c["loan_goal"].astype(str).values
    for gname in fs.loan_goals:
        m[f"goal_{_slug(gname)}"] = (goal == gname).astype(np.int8)
    m["start_dow"] = c["start"].dt.dayofweek.values
    for a in fs.activities:
        m[f"last_{_slug(a)}"] = (m["last_act"].values == a).astype(np.int8)
    m["y"] = c["y"].values
    m["split"] = c["split"].values if "split" in c else None
    return m.drop(columns=["ev_time", "last_act"]).sort_values(["case_id", "t"]).reset_index(drop=True)


def feature_columns(df: pd.DataFrame) -> list[str]:
    drop = {"case_id", "t", "y", "split", "delta_days", "requested_amount"}
    return [c for c in df.columns if c not in drop]


def drop_events(events: pd.DataFrame, rate: float, seed: int, protect_activity: str = "A_Create Application") -> pd.DataFrame:
    """Kịch bản mất sự kiện: xóa ngẫu nhiên `rate` sự kiện, giữ sự kiện bắt đầu."""
    if rate <= 0:
        return events
    rng = np.random.default_rng(seed)
    keep = (rng.random(len(events)) >= rate) | (events["activity"].values == protect_activity)
    return events[keep].reset_index(drop=True)


def cost_and_loss(df: pd.DataFrame, pcfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """c_i = base + min(max_extra, per_offer·#offer); L_i = base + per_amount·RequestedAmount (CU, giả định)."""
    offers = df["cnt_O_Create_Offer"].values if "cnt_O_Create_Offer" in df else np.zeros(len(df))
    c = pcfg["cost"]["base"] + np.minimum(pcfg["cost"]["max_extra"], pcfg["cost"]["per_offer"] * offers)
    L = pcfg["loss"]["base"] + pcfg["loss"]["per_amount"] * df["requested_amount"].values
    return c.astype(float), L.astype(float)
