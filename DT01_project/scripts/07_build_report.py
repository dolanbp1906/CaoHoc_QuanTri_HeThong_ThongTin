"""Bước 7: điền bảng từ CSV kết quả + tài liệu tham khảo đã kiểm chứng vào report.md, xuất Word (.docx).

Chạy: python scripts/07_build_report.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"

REF_ORDER = ["tax2017", "teinemaa2019", "verenich2019", "teinemaa2018", "fahrenkrog2022", "shoush2022", "metzger2019",
             "metzger2020", "bozorgi2023", "kubrak2022", "vandongen2017", "berti2023", "niculescu2005", "zadrozny2002",
             "guo2017", "brier1950", "maisenbacher2017", "gama2014", "chen2016", "breiman2001", "vanderaalst2016",
             "difrancescomarino2018", "maggi2014", "platt1999"]
MANUAL = {  # không có DOI Crossref – nguồn đã đối chiếu thủ công
    "vandongen2017": "van Dongen, B. (2017). BPI Challenge 2017 [Dataset]. 4TU.ResearchData. DOI 10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b (DataCite; xác minh qua API 4TU ngày 14/11/2026).",
    "guo2017": "Guo, C.; Pleiss, G.; Sun, Y.; Weinberger, K. Q. (2017). On Calibration of Modern Neural Networks. Proceedings of the 34th International Conference on Machine Learning (ICML), PMLR 70, 1321–1330.",
    "platt1999": "Platt, J. (1999). Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods. In Advances in Large Margin Classifiers, MIT Press, 61–74.",
}


def ref_text(key, rec):
    if key in MANUAL:
        return MANUAL[key]
    au = rec["authors"]
    auth = "; ".join(a.strip(", ") for a in au[:6]) + ("; et al." if len(au) > 6 else "")
    title = " ".join(rec["title"].replace("<i>", "").replace("</i>", "").split())
    venue = rec.get("venue") or rec.get("publisher") or ""
    vol = f", {rec['volume']}" if rec.get("volume") else ""
    iss = f"({rec['issue']})" if rec.get("issue") else ""
    pg = f", {rec['pages']}" if rec.get("pages") else ""
    return f"{auth} ({rec['year']}). {title}. {venue}{vol}{iss}{pg}. DOI {rec['doi']}"


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def table1():
    rows = [
        ("[1] Tax và cs. (2017)", "Dự báo hoạt động kế tiếp, thời điểm, phần còn lại của vết, remaining time", "LSTM trên tiền tố", "Log công khai (Helpdesk, BPI 2012)", "Đã làm: LSTM đa nhiệm, mã công khai. Chưa xét: xác suất trễ có hiệu chỉnh, phân bổ ngân sách can thiệp"),
        ("[2] Teinemaa và cs. (2019)", "Dự báo kết cục (outcome) theo tiền tố – review và benchmark", "Nhiều cách bucketing/encoding + bộ phân lớp (RF, XGBoost, LR, SVM)", "Nhiều log thật, gồm BPI 2017", "Đã làm: benchmark lớn, mã hóa tổng hợp + cây thường mạnh. Chưa xét: độ hiệu chỉnh, quyết định can thiệp"),
        ("[3] Verenich và cs. (2019)", "Dự báo thời gian còn lại – survey và cross-benchmark", "So sánh nhiều phương pháp hồi quy/học sâu", "Nhiều log thật", "Đã làm: so sánh thống nhất. Chưa xét: chuyển dự báo thành quyết định dưới ngân sách"),
        ("[4] Teinemaa và cs. (2018)", "Prescriptive: phát cảnh báo để giảm kết cục xấu", "Ngưỡng cảnh báo trên xác suất, mô hình chi phí (can thiệp, hiệu quả giảm thiểu, kết cục xấu)", "Log thật", "Đã làm: khung chi phí cho cảnh báo. Chưa xét: ngân sách chung cho nhiều hồ sơ cạnh tranh, censoring"),
        ("[5] Fahrenkrog-Petersen và cs. (2022)", "Mở rộng hệ cảnh báo: cảnh báo ngay hay chờ", "Khung alarm-based có xét thời điểm", "Nhiều log thật", "Đã làm: quyết định thời điểm cảnh báo. Chưa xét: knapsack theo ngân sách mỗi epoch"),
        ("[6] Shoush & Dumas (2022)", "Prescriptive dưới ràng buộc nguồn lực", "Suy luận nhân quả ước lượng hiệu ứng can thiệp để ưu tiên hồ sơ", "Log thật", "Đã làm: ưu tiên theo hiệu ứng khi nguồn lực có hạn. Chưa xét (theo hiểu biết): chi phí–thiệt hại không đồng nhất, hiệu chỉnh dưới drift"),
        ("[7] Metzger và cs. (2019)", "Thích nghi quy trình chủ động", "Ensemble học sâu cho ước lượng độ tin cậy của dự báo", "Dữ liệu thật", "Đã làm: dùng độ tin cậy để quyết định thích nghi. Chưa xét: phân bổ ngân sách giữa nhiều hồ sơ"),
        ("[8] Metzger và cs. (2020)", "Khi nào kích hoạt thích nghi", "Học tăng cường trực tuyến trên dự báo + độ tin cậy", "Dữ liệu thật", "Đã làm: học chính sách kích hoạt. Chưa xét: tối ưu chính xác dưới ngân sách cố định"),
        ("[9] Bozorgi và cs. (2023)", "Học khi nào can thiệp", "Suy luận nhân quả + học tăng cường", "Log thật", "Đã làm: kết hợp hiệu ứng nhân quả và thời điểm. Chưa xét: đánh giá tác động của hiệu chỉnh xác suất lên quyết định"),
        ("[10] Kubrak và cs. (2022)", "Tổng quan prescriptive process monitoring", "Rà soát tài liệu có hệ thống", "—", "Đã làm: phân loại mục tiêu, loại can thiệp, nguồn dữ liệu. Chưa xét: thực nghiệm"),
        ("[17] Maisenbacher & Weidlich (2017)", "Concept drift trong PPM", "Học tăng dần", "Log mô phỏng/thật", "Đã làm: cập nhật mô hình khi drift. Chưa xét: drift làm hỏng bộ hiệu chỉnh và quyết định ngân sách"),
        ("[13] Niculescu-Mizil & Caruana (2005)", "Chất lượng xác suất của bộ học có giám sát", "Platt scaling, isotonic regression", "Bộ dữ liệu chuẩn (không phải quy trình)", "Đã làm: so sánh hiệu chỉnh. Chưa xét: dữ liệu theo thời gian, dịch chuyển phân phối"),
        ("[15] Guo và cs. (2017)", "Hiệu chỉnh mạng nơ-ron hiện đại", "ECE, temperature scaling", "Ảnh/văn bản", "Đã làm: chuẩn hóa ECE. Chưa xét: validation và test khác phân phối"),
    ]
    return md_table(pd.DataFrame(rows, columns=["Công trình", "Bài toán", "Phương pháp", "Dữ liệu", "Đã làm – chưa xét so với đề tài"]))


def table2():
    card = json.loads((R / "dataset_card.json").read_text(encoding="utf-8"))["tau_14"]["splits"]
    names = {"train": "Train (01–07/2016)", "valcal": "Valcal (08/2016)", "valsel": "Valsel (09/2016)", "test": "Test (10–12/2016)"}
    rows = []
    for k in ("train", "valcal", "valsel", "test"):
        v = card[k]
        cens = v["label_status"].get("censored_known_late", 0)
        rows.append({"Tập": names[k], "Hồ sơ": f"{v['cases']:,}".replace(",", "."), "Tỷ lệ trễ (hồ sơ)": f"{v['late_share']*100:.1f}%",
                     "Snapshot": f"{v['snapshots']:,}".replace(",", "."), "Tỷ lệ trễ (snapshot)": f"{v['snapshot_late_share']*100:.1f}%",
                     "Censored đã chắc trễ": cens})
    t = md_table(pd.DataFrame(rows))
    return t + "\n\n*Bảng 2. Thông tin dữ liệu với τ = 14 ngày (giả định). Nhãn: thật (quan sát), trừ 98 hồ sơ chưa kết thúc được gán trễ vì đã quan sát > τ. Giấy phép: 4TU General Terms of Use. 79 đặc trưng/snapshot.*"


def table3():
    t = pd.read_csv(R / "table3_models.csv")
    t = t[["Mô hình", "Hiệu chỉnh", "AUC-ROC", "AUC-PR", "F1", "Brier", "ECE", "ECE (valsel)", "Huấn luyện (s)"]]
    return md_table(t) + "\n\n*Bảng 3. Hiệu quả dự báo trên test (mean ± SD qua 10 seeds; LR tất định nên SD = 0). F1 tại ngưỡng chọn trên valsel. Thời gian huấn luyện cho một seed trên toàn bộ train (213.363 snapshot).*"


def table3b():
    t = pd.read_csv(R / "table3b_policy_main.csv")
    return md_table(t) + "\n\n*Bảng 3b. Mô phỏng chính sách trên test, B = 10% tổng chi phí ứng viên mỗi tuần, e = 0,3, 15 epoch, 10 seeds (mean ± SD). Mô hình: XGBoost; nguồn xác suất mặc định Platt-val (được chọn trên valsel). CI 95%: bootstrap trên chênh lệch cặp theo seed. Biến thể \"hiệu chỉnh trên test\" là trần chẩn đoán, không hợp lệ để kết luận.*"


def table4():
    p = pd.read_csv(R / "policy_main_tau14.csv")
    keep = {"random": "Random", "deadline_first": "Deadline-first", "risk_first": "Risk-first", "cis_knapsack": "CIS (Platt-val)",
            "cis_knapsack_raw": "CIS (p thô)", "oracle": "Oracle"}
    g = p[p.policy.isin(keep)].groupby(["scenario", "budget", "effect", "policy"]).net_benefit.mean().unstack("policy")[list(keep)]
    g = g.rename(columns=keep).reset_index()
    g["budget"] = (g["budget"] * 100).round().astype(int).astype(str) + "%"
    g = g.rename(columns={"scenario": "Kịch bản", "budget": "B", "effect": "e"})
    for c in keep.values():
        g[c] = g[c].round(0).astype(int)
    return md_table(g) + "\n\n*Bảng 4. Lợi ích ròng mô phỏng (CU, trung bình 10 seeds) theo ngân sách, hiệu quả can thiệp và kịch bản (const: e hằng; decay: e giảm khi sát hạn; homog: c ≡ 1, L ≡ 10).*"


def stress_section():
    out = []
    c = pd.read_csv(R / "stress_censor.csv")
    s = c.groupby("variant").agg(rows=("n_train_rows", "mean"), late=("train_late_share", "mean"), mp=("mean_p", "mean"),
                                 auc=("auc_roc", "mean"), brier=("brier", "mean"), ece=("ece", "mean"),
                                 cis=("net_cis_knapsack", "mean"), risk=("net_risk_first", "mean"))
    lab = {"naive_zero": "Gán 0 cho mọi hồ sơ chưa kết thúc (sai)", "drop_all_open": "Loại mọi hồ sơ chưa kết thúc",
           "correct": "Đúng: giữ hồ sơ chắc trễ, loại hồ sơ chưa biết"}
    rows = [{"Cách xử lý": lab[v], "Mẫu train": f"{int(r.rows):,}".replace(",", "."), "Tỷ lệ trễ train": f"{r.late:.3f}",
             "TB xác suất (test)": f"{r.mp:.3f}", "AUC": f"{r.auc:.3f}", "Brier": f"{r.brier:.4f}", "ECE": f"{r.ece:.3f}",
             "Lợi ích CIS": f"{r.cis:.0f}", "Lợi ích Risk-first": f"{r.risk:.0f}"} for v, r in s.loc[["naive_zero", "drop_all_open", "correct"]].iterrows()]
    st = c.iloc[0]
    out.append("**Censoring.** Mô phỏng tình huống trích xuất dữ liệu huấn luyện sớm vào 01/08/2016: trong 17.345 hồ sơ train, "
               f"{int(st['status_observed']):,} đã có kết quả, {int(st['status_censored_known_late']):,} chưa kết thúc nhưng đã chắc trễ, "
               f"{int(st['status_censored_unknown']):,} chưa biết nhãn. Mô hình XGBoost (xác suất thô) được huấn luyện theo ba cách gán nhãn và đánh giá trên cùng tập test với nhãn thật (10 seeds).".replace(",", "."))
    out.append(md_table(pd.DataFrame(rows)) + "\n\n*Bảng 5. Ảnh hưởng của cách xử lý hồ sơ censored (trung bình 10 seeds; lợi ích ròng ở B = 10%, e = 0,3).*")
    n, d, k = s.loc["naive_zero"], s.loc["drop_all_open"], s.loc["correct"]
    out.append(f"Gán \"không trễ\" cho hồ sơ chưa kết thúc làm tỷ lệ trễ train giảm từ {k.late:.3f} xuống {n.late:.3f}, xác suất trung bình trên test bị kéo xuống {n.mp:.3f} (thực tế 0,719), ECE tăng từ {k.ece:.3f} lên {n.ece:.3f} và AUC giảm từ {k.auc:.3f} xuống {n.auc:.3f}. "
               f"Risk-first mất {(1 - n.risk / k.risk) * 100:.0f}% lợi ích ròng; CIS chỉ mất {(1 - n.cis / k.cis) * 100:.1f}% vì chi phí–thiệt hại vẫn chi phối lựa chọn. "
               f"Loại mọi hồ sơ chưa kết thúc tránh được phần lớn sai lệch nhưng vẫn làm ECE gấp đôi so với cách đúng ({d.ece:.3f} so với {k.ece:.3f}) do bỏ đi các hồ sơ chậm nhất.")
    import re
    out[-1] = re.sub(r"(\d)\.(\d)", r",", out[-1])
    if (R / "stress_missing.csv").exists():
        m = pd.read_csv(R / "stress_missing.csv")
        g = m.groupby(["where", "missing_rate"]).agg(auc=("auc_roc", "mean"), brier=("brier", "mean"), ece=("ece", "mean"),
                                                      cis=("net_cis_knapsack", "mean"), risk=("net_risk_first", "mean"),
                                                      orc=("net_oracle", "mean")).reset_index()
        g["cis_r"] = (g["cis"] / g["orc"] * 100).round(1).astype(str) + "%"
        g["risk_r"] = (g["risk"] / g["orc"] * 100).round(1).astype(str) + "%"
        g = g.drop(columns=["orc"])
        g["where"] = g["where"].map({"test_only": "Chỉ log test", "all": "Mọi tập"})
        g["missing_rate"] = (g["missing_rate"] * 100).round().astype(int).astype(str) + "%"
        g.columns = ["Mất sự kiện ở", "Tỷ lệ mất", "AUC", "Brier", "ECE", "Lợi ích CIS", "Lợi ích Risk-first", "CIS / Oracle", "Risk-first / Oracle"]
        for col, nd in (("AUC", 3), ("Brier", 4), ("ECE", 3), ("Lợi ích CIS", 0), ("Lợi ích Risk-first", 0)):
            g[col] = g[col].round(nd)
        g["Lợi ích CIS"] = g["Lợi ích CIS"].astype(int)
        g["Lợi ích Risk-first"] = g["Lợi ích Risk-first"].astype(int)
        out.append("**Mất sự kiện.** Xóa ngẫu nhiên 0/10/30% sự kiện (giữ sự kiện bắt đầu), hoặc chỉ ở log test (mô hình học trên log sạch, triển khai trên log kém), hoặc ở mọi tập (3 seeds, mỗi seed một mẫu xóa khác nhau).")
        out.append(md_table(g) + "\n\n*Bảng 6. Ảnh hưởng của mất sự kiện (XGBoost, xác suất thô; B = 10%, e = 0,3).*")
        out.append("MISSING_COMMENT")
    if (R / "stress_tau.csv").exists():
        t = pd.read_csv(R / "stress_tau.csv")
        g = t.groupby(["tau", "p_source"]).agg(auc=("auc_roc", "mean"), ece=("ece", "mean"), cis=("net_cis_knapsack", "mean"),
                                                risk=("net_risk_first", "mean"), dl=("net_deadline_first", "mean"),
                                                orc=("net_oracle", "mean")).reset_index()
        g["p_source"] = g["p_source"].map({"p_raw": "Thô", "p_platt": "Platt-val", "p_platt_oof": "Platt-OOF"})
        g.columns = ["τ (ngày)", "Nguồn p", "AUC", "ECE", "Lợi ích CIS", "Risk-first", "Deadline-first", "Oracle"]
        for col in ("Lợi ích CIS", "Risk-first", "Deadline-first", "Oracle"):
            g[col] = g[col].round(0).astype(int)
        g["AUC"], g["ECE"] = g["AUC"].round(3), g["ECE"].round(3)
        out.append("**Độ nhạy theo τ.** Lặp lại toàn bộ quy trình (XGBoost, 10 seeds) với τ = 10 và 21 ngày.")
        out.append(md_table(g) + "\n\n*Bảng 7. Độ nhạy theo ngưỡng τ (B = 10%, e = 0,3; trung bình 10 seeds).*")
        out.append("TAU_COMMENT")
    d = pd.read_csv(R / "stress_drift.csv")
    dd = d.groupby(["month", "p_source"]).agg(late=("late_share", "mean"), ece=("ece", "mean"), auc=("auc", "mean")).reset_index()
    piv = dd.pivot(index="month", columns="p_source", values="ece")
    late = dd.groupby("month").late.first()
    auc = dd[dd.p_source == "p_raw"].set_index("month").auc
    rows = [{"Tháng": mth, "Tỷ lệ trễ thực": f"{late[mth]:.3f}", "AUC": f"{auc[mth]:.3f}", "ECE thô": f"{piv.loc[mth, 'p_raw']:.3f}",
             "ECE Platt-val": f"{piv.loc[mth, 'p_platt']:.3f}", "ECE Platt-OOF": f"{piv.loc[mth, 'p_platt_oof']:.3f}"} for mth in piv.index]
    out.append("**Drift theo tháng.** Tỷ lệ snapshot trễ tăng từ 66,8% (01/2016) lên 78,3% (08/2016) rồi giảm về 71–74% ở 10–12/2016 (Hình 4). Bảng 8 cho thấy AUC dao động 0,74–0,79 theo tháng; hai bộ hiệu chỉnh fit trên valcal (Platt-val, Isotonic-val) có ECE cao nhất ở mọi tháng test (0,04–0,07), trong khi p thô và Platt-OOF ở mức 0,01–0,03.")
    out.append(md_table(pd.DataFrame(rows)) + "\n\n*Bảng 8. Chất lượng dự báo theo tháng trên test (XGBoost, trung bình 10 seeds). Tháng 01/2017 chỉ gồm hồ sơ bắt đầu cuối 12/2016.*")
    out.append("**Trả lời RQ3.** RQ3_COMMENT")
    return "\n\n".join(out)


def main():
    md = (ROOT / "report" / "report.md").read_text(encoding="utf-8")
    refs = json.loads((R / "references_verified.json").read_text(encoding="utf-8"))
    ref_lines = []
    for i, k in enumerate(REF_ORDER, 1):
        rec = refs.get(k, {})
        if k not in MANUAL and not (rec.get("verified") or k == "kubrak2022"):
            print("BỎ tài liệu chưa kiểm chứng:", k)
            continue
        ref_lines.append(f"[{i}] {ref_text(k, rec)}")
    comments = json.loads((ROOT / "report" / "comments.json").read_text(encoding="utf-8")) if (ROOT / "report" / "comments.json").exists() else {}
    stress = stress_section()
    for k, v in comments.items():
        stress = stress.replace(k, v)
    md = (md.replace("TABLE1_PLACEHOLDER", table1() + "\n\n*Bảng 1. So sánh công trình liên quan.*")
          .replace("TABLE2_PLACEHOLDER", table2()).replace("TABLE3_PLACEHOLDER", table3())
          .replace("TABLE3B_PLACEHOLDER", table3b()).replace("TABLE4_PLACEHOLDER", table4())
          .replace("STRESS_PLACEHOLDER", stress).replace("REFS_PLACEHOLDER", "\n\n".join(ref_lines)))
    left = [w for w in ("PLACEHOLDER", "_COMMENT") if w in md]
    if left:
        print("CẢNH BÁO: còn placeholder:", left)
    out_md = ROOT / "report" / "report_final.md"
    out_md.write_text(md, encoding="utf-8")
    print("written", out_md)


if __name__ == "__main__":
    main()
