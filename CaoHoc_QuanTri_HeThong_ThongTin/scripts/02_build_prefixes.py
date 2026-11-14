"""Bước 2: gán nhãn theo τ, chia theo thời gian, dựng snapshot tiền tố + đặc trưng, xuất manifest.

Chạy: python scripts/02_build_prefixes.py --taus 10,14,21
"""
import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import data, features  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(events, cfg, tau, extraction_time=None, tag=""):
    cases = data.build_cases(events, cfg, tau, extraction_time)
    cases["split"] = data.assign_split(cases, cfg)
    tr_ids = cases.index[cases["split"] == "train"]
    fs = features.FeatureSpace.fit(events[events["case_id"].isin(tr_ids)], cases.loc[tr_ids])
    evcum = features.event_level_cumulative(events[events["timestamp"] <= cases["extraction"].iloc[0]], fs)
    snap = features.make_snapshots(cases, tau, cfg["snapshots"]["hour_utc"])
    X = features.snapshot_features(snap, evcum, cases, fs, tau)
    return cases, X


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--taus", default=None)
    args = ap.parse_args()
    cfg = data.load_config(args.config)
    taus = [float(t) for t in args.taus.split(",")] if args.taus else cfg["label"]["tau_sensitivity"]
    events = data.load_events(cfg)
    out_dir = ROOT / "data" / "processed"
    card = {}
    for tau in taus:
        cases, X = build(events, cfg, tau)
        t = int(tau)
        X.to_parquet(out_dir / f"snap_tau{t}.parquet", index=False)
        cases.to_parquet(out_dir / f"cases_tau{t}.parquet")
        stats = {}
        for sp, g in cases.groupby("split"):
            xs = X[X["split"] == sp]
            stats[sp] = {"cases": int(len(g)), "late_share": round(float(g["y"].mean()), 4),
                         "label_status": g["label_status"].value_counts().to_dict(),
                         "snapshots": int(len(xs)), "snapshot_late_share": round(float(xs["y"].mean()), 4),
                         "start_min": str(g["start"].min()), "start_max": str(g["start"].max())}
        card[f"tau_{t}"] = {"n_features": len(features.feature_columns(X)), "splits": stats}
        print(f"τ={t}: snapshots={len(X):,}; features={len(features.feature_columns(X))}")
        if t == int(cfg["label"]["tau_days"]):
            cases[["start", "split", "label_status", "y"]].to_csv(ROOT / "results" / "split_index_tau14.csv")
    (ROOT / "results" / "dataset_card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")

    raw = ROOT / cfg["data"]["raw"]
    prof = json.loads((ROOT / "results" / "data_profile.json").read_text(encoding="utf-8"))
    c14 = pd.read_parquet(out_dir / "cases_tau14.parquet")
    manifest = pd.DataFrame([{
        "dataset_name": "BPI Challenge 2017",
        "source_url": cfg["data"]["source_url"],
        "doi": cfg["data"]["doi"],
        "version/download_date": f"v1 / {date.today().isoformat()}",
        "schema": "case_id, activity, timestamp, resource, lifecycle, LoanGoal, ApplicationType, RequestedAmount",
        "original_n": f"{prof['n_events']} events; {prof['n_cases']} cases",
        "filtered_n": f"{int(c14['y'].notna().sum())} cases with known label (tau=14)",
        "split_policy": "temporal by case start: train<2016-08-01; valcal 08/2016; valsel 09/2016; test>=2016-10-01",
        "sha256": sha256(raw),
        "license": cfg["data"]["license"],
        "notes": "Không phân phối lại log; dùng script tải. tau=14 ngày là kịch bản nghiên cứu, không phải SLA thật.",
    }])
    manifest.to_csv(ROOT / "results" / "manifest.csv", index=False)
    print(json.dumps(card, indent=1, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
