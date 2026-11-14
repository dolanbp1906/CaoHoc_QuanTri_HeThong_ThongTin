"""Kiểm chứng DOI ứng viên qua Crossref (có thử lại). Chỉ tài liệu khớp tiêu đề mới được đưa vào báo cáo.

Chạy: python scripts/verify_dois.py
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

CANDIDATES = {
    "tax2017": ("10.1007/978-3-319-59536-8_30", "Predictive Business Process Monitoring with LSTM Neural Networks"),
    "teinemaa2019": ("10.1145/3301300", "Outcome-Oriented Predictive Process Monitoring"),
    "verenich2019": ("10.1145/3331449", "Survey and Cross-benchmark Comparison of Remaining Time Prediction Methods"),
    "fahrenkrog2022": ("10.1007/s10115-021-01633-w", "Fire now, fire later"),
    "teinemaa2018": ("10.1007/978-3-319-98651-7_6", "Alarm-Based Prescriptive Process Monitoring"),
    "shoush2022": ("10.1007/978-3-030-98581-3_14", "Prescriptive Process Monitoring Under Resource Constraints"),
    "bozorgi2021": ("10.1109/ICPM53251.2021.9576858", "Prescriptive process monitoring for cost-aware cycle time reduction"),
    "kubrak2022": ("10.7717/peerj-cs.1097", "Prescriptive process monitoring: Quo vadis"),
    "metzger2019": ("10.1007/978-3-030-21290-2_34", "Proactive Process Adaptation Using Deep Learning Ensembles"),
    "metzger2020": ("10.1007/978-3-030-58666-9_16", "Triggering Proactive Business Process Adaptations via Online Reinforcement Learning"),
    "bozorgi2023": ("10.1007/978-3-031-34560-9_22", "Learning When to Treat Business Processes"),
    "niculescu2005": ("10.1145/1102351.1102430", "Predicting good probabilities with supervised learning"),
    "zadrozny2002": ("10.1145/775047.775151", "Transforming classifier scores into accurate multiclass probability estimates"),
    "brier1950": ("10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2", "VERIFICATION OF FORECASTS EXPRESSED IN TERMS OF PROBABILITY"),
    "gama2014": ("10.1145/2523813", "A survey on concept drift adaptation"),
    "maisenbacher2017": ("10.1109/SCC.2017.10", "Handling Concept Drift in Predictive Process Monitoring"),
    "chen2016": ("10.1145/2939672.2939785", "XGBoost"),
    "vanderaalst2016": ("10.1007/978-3-662-49851-4", "Process Mining"),
    "berti2023": ("10.1016/j.simpa.2023.100556", "PM4Py"),
    "difrancescomarino2018": ("10.1007/978-3-319-98648-7_27", "Predictive Process Monitoring Methods: Which One Suits Me Best"),
    "breiman2001": ("10.1023/A:1010933404324", "Random Forests"),
    "maggi2014": ("10.1007/978-3-319-07881-6_31", "Predictive Monitoring of Business Processes"),
    "vandongen2017": ("10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b", "BPI Challenge 2017"),
}


def fetch(doi, tries=5):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-script/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=40))["message"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"_error": "404"}
        except Exception:  # noqa: BLE001
            time.sleep(3 * (k + 1))
    return {"_error": "network"}


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


out = {}
for key, (doi, expect) in CANDIDATES.items():
    m = fetch(doi)
    if "_error" in m:
        rec = {"doi": doi, "verified": False, "error": m["_error"]}
    else:
        title = (m.get("title") or [""])[0]
        authors = [f"{a.get('family', '')}, {a.get('given', '')}" for a in m.get("author", [])]
        date = (m.get("published-print") or m.get("published-online") or m.get("issued") or {}).get("date-parts", [[None]])[0]
        rec = {"doi": doi, "title": title, "authors": authors, "year": date[0],
               "venue": (m.get("container-title") or [""])[0], "volume": m.get("volume"), "issue": m.get("issue"),
               "pages": m.get("page"), "publisher": m.get("publisher"), "type": m.get("type"),
               "verified": norm(expect) in norm(title) or norm(title) in norm(expect)}
    out[key] = rec
    print(key, rec.get("verified"), rec.get("year"), (rec.get("title") or rec.get("error"))[:90], flush=True)
Path("results/references_verified.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
