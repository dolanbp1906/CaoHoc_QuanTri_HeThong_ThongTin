"""Bước 1: đọc XES, chuẩn hóa cột, kiểm tra trùng/thứ tự thời gian, lưu Parquet và in hồ sơ dữ liệu.

Chạy: python scripts/01_profile_events.py --input data/raw/bpi2017.xes.gz
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/raw/bpi2017.xes.gz")
    ap.add_argument("--output", default="data/processed/events.parquet")
    args = ap.parse_args()

    import pm4py  # import muộn để --help chạy nhanh

    df = pm4py.read_xes(str(ROOT / args.input))
    df = df.rename(columns={
        "case:concept:name": "case_id",
        "concept:name": "activity",
        "time:timestamp": "timestamp",
        "org:resource": "resource",
        "lifecycle:transition": "lifecycle",
        "case:LoanGoal": "loan_goal",
        "case:ApplicationType": "app_type",
        "case:RequestedAmount": "requested_amount",
    })
    keep = ["case_id", "activity", "timestamp", "resource", "lifecycle", "loan_goal", "app_type", "requested_amount", "EventID"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    n_raw = len(df)

    # Kiểm tra trùng sự kiện hoàn toàn
    dup = df.duplicated(subset=["case_id", "activity", "timestamp", "lifecycle"]).sum()
    # Thứ tự ổn định: theo case, timestamp, rồi thứ tự xuất hiện trong file (quy tắc phá hòa)
    df["file_order"] = range(len(df))
    df = df.sort_values(["case_id", "timestamp", "file_order"], kind="mergesort").reset_index(drop=True)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    g = df.groupby("case_id")["timestamp"]
    start, end = g.min(), g.max()
    dur_days = (end - start).dt.total_seconds() / 86400
    last_act = df.groupby("case_id")["activity"].last()
    profile = {
        "n_events": int(n_raw),
        "n_cases": int(df["case_id"].nunique()),
        "n_activities": int(df["activity"].nunique()),
        "n_resources": int(df["resource"].nunique()),
        "exact_duplicates": int(dup),
        "time_min": str(df["timestamp"].min()),
        "time_max": str(df["timestamp"].max()),
        "case_duration_days": dur_days.describe(percentiles=[0.25, 0.5, 0.75, 0.9]).round(2).to_dict(),
        "share_duration_gt_14d": round(float((dur_days > 14).mean()), 4),
        "top_last_activities": last_act.value_counts().head(12).to_dict(),
        "lifecycle_values": df["lifecycle"].value_counts().to_dict() if "lifecycle" in df else {},
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "data_profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    print("\nActivities:")
    print(df["activity"].value_counts().to_string())


if __name__ == "__main__":
    main()
