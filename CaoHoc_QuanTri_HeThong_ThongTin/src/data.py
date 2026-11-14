"""Tải nhật ký sự kiện, dựng bảng hồ sơ, gán nhãn trễ có xử lý right-censoring, chia theo thời gian."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DAY = pd.Timedelta(days=1)


def load_config(path: str | Path = "configs/default.yaml") -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_events(cfg: dict) -> pd.DataFrame:
    ev = pd.read_parquet(ROOT / cfg["data"]["events"])
    ev["timestamp"] = pd.to_datetime(ev["timestamp"], utc=True)
    # Thứ tự ổn định: case, timestamp, thứ tự trong file (quy tắc phá hòa cố định)
    return ev.sort_values(["case_id", "timestamp", "file_order"], kind="mergesort").reset_index(drop=True)


def build_cases(events: pd.DataFrame, cfg: dict, tau_days: float, extraction_time=None) -> pd.DataFrame:
    """Bảng một dòng/hồ sơ.

    T_c    = thời điểm sự kiện kết quả đầu tiên (A_Pending/A_Denied/A_Cancelled) − thời điểm bắt đầu (ngày)
    U_c    = extraction_time − bắt đầu (ngày): thời gian quan sát được của hồ sơ chưa kết thúc
    y      = 1[T_c > τ] nếu đã kết thúc trước extraction; 1 nếu chưa kết thúc nhưng U_c > τ (đã chắc trễ);
             NaN nếu chưa kết thúc và U_c ≤ τ (CHƯA BIẾT – không được gán 0).
    """
    dcfg = cfg["data"]
    ext = pd.Timestamp(extraction_time or dcfg["extraction_time"])
    if ext.tzinfo is None:
        ext = ext.tz_localize("UTC")
    ev = events[events["timestamp"] <= ext]
    g = ev.groupby("case_id", sort=True)
    cases = pd.DataFrame({
        "start": g["timestamp"].min(),
        "requested_amount": g["requested_amount"].first(),
        "loan_goal": g["loan_goal"].first(),
        "app_type": g["app_type"].first(),
    })
    term = ev[ev["activity"].isin(dcfg["terminal_activities"])]
    tg = term.groupby("case_id")
    cases["t_end"] = tg["timestamp"].min()
    cases["outcome"] = tg["activity"].first()
    cases["T_days"] = (cases["t_end"] - cases["start"]) / DAY
    cases["U_days"] = (ext - cases["start"]) / DAY
    cases["observed"] = cases["t_end"].notna()
    tau = float(tau_days)
    y = pd.Series(np.nan, index=cases.index)
    y[cases["observed"]] = (cases.loc[cases["observed"], "T_days"] > tau).astype(float)
    known_late = (~cases["observed"]) & (cases["U_days"] > tau)
    y[known_late] = 1.0
    cases["y"] = y
    cases["label_status"] = np.select(
        [cases["observed"], known_late], ["observed", "censored_known_late"], default="censored_unknown")
    cases["deadline"] = cases["start"] + pd.to_timedelta(tau, unit="D")
    cases["extraction"] = ext
    return cases


def assign_split(cases: pd.DataFrame, cfg: dict) -> pd.Series:
    s = cfg["split"]
    t1, t2, t3 = (pd.Timestamp(s[k], tz="UTC") for k in ("train_end", "valcal_end", "val_end"))
    st = cases["start"]
    return pd.Series(np.select([st < t1, st < t2, st < t3], ["train", "valcal", "valsel"], default="test"),
                     index=cases.index, name="split")
