"""Baseline dự báo trên tiền tố và bộ hiệu chỉnh xác suất (Platt / Isotonic) học trên tập validation riêng."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def make_model(name: str, params: dict, seed: int):
    if name == "lr":
        return make_pipeline(StandardScaler(), LogisticRegression(C=params["C"], max_iter=params["max_iter"]))
    if name == "rf":
        return RandomForestClassifier(n_estimators=params["n_estimators"], min_samples_leaf=params["min_samples_leaf"],
                                      max_features=params["max_features"], n_jobs=params["n_jobs"], random_state=seed)
    if name == "xgb":
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=params["n_estimators"], max_depth=params["max_depth"],
                             learning_rate=params["learning_rate"], subsample=params["subsample"],
                             colsample_bytree=params["colsample_bytree"], n_jobs=params["n_jobs"],
                             random_state=seed, tree_method="hist", eval_metric="logloss")
    raise ValueError(name)


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


class Calibrator:
    """raw: giữ nguyên; platt: p = σ(a·logit(ŝ)+b); isotonic: p = g(ŝ), g đơn điệu không giảm."""

    def __init__(self, method: str):
        self.method = method
        self.m = None

    def fit(self, s, y):
        if self.method == "platt":
            self.m = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(s).reshape(-1, 1), y)
        elif self.method == "isotonic":
            self.m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s, y)
        return self

    def predict(self, s):
        if self.method == "raw":
            return np.asarray(s, float)
        if self.method == "platt":
            return self.m.predict_proba(_logit(s).reshape(-1, 1))[:, 1]
        return self.m.predict(s)
