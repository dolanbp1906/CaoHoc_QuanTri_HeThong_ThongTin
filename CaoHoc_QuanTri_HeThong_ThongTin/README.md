# ĐT01 – Ưu tiên can thiệp giảm nguy cơ trễ hạn bằng Process Mining và dự báo có hiệu chỉnh

*Calibrated and Cost-Aware Intervention Prioritization in Business Process Monitoring* – CSE631.

Repo tái lập toàn bộ thực nghiệm của bài tập lớn: đọc log BPI Challenge 2017, dựng tiền tố, huấn luyện ≥2 baseline,
hiệu chỉnh xác suất, mô phỏng chính sách can thiệp dưới ngân sách, ablation và stress test.

> **Giới hạn quan trọng.** τ = 14 ngày là kịch bản nghiên cứu, **không phải SLA thật** của ngân hàng.
> Chi phí c, thiệt hại L và hiệu quả can thiệp e là **giả định thí nghiệm**; dữ liệu là observational nên mọi
> kết quả về lợi ích can thiệp chỉ là **tối ưu trong mô phỏng**, không phải bằng chứng nhân quả.

## Cấu trúc

```
configs/default.yaml        mọi tham số (τ, split, mô hình, ngân sách, chi phí, seeds)
src/data.py                 bảng hồ sơ, nhãn trễ, right-censoring, chia theo thời gian
src/features.py             snapshot hằng ngày, đặc trưng tiền tố (merge_asof, không nhìn tương lai), mất sự kiện
src/models.py               LR, RF, XGBoost; hiệu chỉnh Platt / Isotonic
src/metrics.py              AUC-ROC, AUC-PR, F1, Brier, ECE, reliability, bootstrap theo case
src/policy.py               Random, Deadline-first, Risk-first, CIS-greedy, CIS-knapsack (MILP/HiGHS), Oracle
scripts/01_profile_events.py  XES → Parquet, hồ sơ dữ liệu
scripts/02_build_prefixes.py  snapshot + đặc trưng cho τ ∈ {10,14,21}, manifest.csv
scripts/03_train.py           3 mô hình × 4 cách hiệu chỉnh × 10 seeds
scripts/04_calibrate_policy.py  mô phỏng chính sách paired-budget
scripts/05_stress.py          censoring, mất sự kiện, τ, drift theo tháng
scripts/06_report_assets.py   bảng + hình cho báo cáo
tests/test_core.py            31 unit test (ví dụ tính tay, MILP = DP, không rò rỉ)
results/                      CSV kết quả thô, manifest, dataset card, log, môi trường
figures/                      hình
```

## Cài đặt (Windows, Python 3.11)

```bash
python -m venv .venv && .venv\Scripts\activate
python -m pip install -r requirements.txt
set PYTHONIOENCODING=utf-8      # console Windows cần UTF-8 để in ký tự τ
```

Ghi chú môi trường đã chạy: `pm4py` cần gỡ gói phụ `cvxopt` nếu Windows Application Control chặn DLL;
`ortools` bị chặn tương tự nên bài toán knapsack được giải bằng `scipy.optimize.milp` (HiGHS) và kiểm chứng
bằng quy hoạch động trong unit test.

## Tải dữ liệu (không phân phối lại log)

```bash
curl -L -o data/raw/bpi2017.xes.gz "https://data.4tu.nl/file/34c3f44b-3101-4ea9-8281-e38905c68b8d/f3aec4f7-d52c-4217-82f4-57d719a8298c"
# MD5 công bố: 10b37a2f78e870d78406198403ff13d2
```

## Chạy lại toàn bộ

```bash
python -m pytest -q tests                      # chạy trước: ví dụ toy phải khớp
python scripts/01_profile_events.py
python scripts/02_build_prefixes.py
python scripts/03_train.py --tag main          # ~15 phút CPU 12 luồng
python scripts/04_calibrate_policy.py --tag main
python scripts/05_stress.py
python scripts/06_report_assets.py
python scripts/verify_dois.py                  # kiểm chứng DOI tài liệu tham khảo qua Crossref
python scripts/07_build_report.py              # điền bảng/tài liệu vào report/report_final.md
python scripts/08_to_docx.py                   # xuất report/BaoCao_DT01.docx
```

Seeds 1001–1010. Chia theo thời điểm bắt đầu hồ sơ: train < 08/2016; valcal = 08/2016 (fit bộ hiệu chỉnh);
valsel = 09/2016 (chọn mô hình/ngưỡng); test ≥ 10/2016. Tập test không được dùng để chọn tham số
(ngoại lệ duy nhất là biến thể *chẩn đoán* `cis_knapsack_testcal`, ghi rõ là trần tham chiếu, không dùng để kết luận).
