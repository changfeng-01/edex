from __future__ import annotations

from typing import Any, Sequence

import pandas as pd


def _fallback_models(reason: str = "insufficient_data") -> dict[str, Any]:
    return {"model_status": "insufficient_data", "unavailable_reason": reason}


def train_level_classifier(history: pd.DataFrame, feature_cols: Sequence[str]) -> dict[str, Any]:
    if len(history) < 4 or "level_label" not in history.columns or history["level_label"].nunique() < 2:
        return _fallback_models()
    from sklearn.ensemble import RandomForestClassifier

    model = RandomForestClassifier(n_estimators=64, random_state=42)
    model.fit(history[list(feature_cols)].fillna(0.0), history["level_label"])
    return {"model": model, "model_status": "ok"}


def train_score_regressor(history: pd.DataFrame, feature_cols: Sequence[str]) -> dict[str, Any]:
    if len(history) < 4 or "overall_score" not in history.columns:
        return _fallback_models()
    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(n_estimators=64, random_state=42)
    model.fit(history[list(feature_cols)].fillna(0.0), pd.to_numeric(history["overall_score"], errors="coerce").fillna(0.0))
    return {"model": model, "model_status": "ok"}


def train_hard_pass_classifier(history: pd.DataFrame, feature_cols: Sequence[str]) -> dict[str, Any]:
    hard_col = "hard_constraint_passed" if "hard_constraint_passed" in history.columns else "hard_pass"
    if len(history) < 4 or hard_col not in history.columns or history[hard_col].nunique() < 2:
        return _fallback_models()
    from sklearn.ensemble import RandomForestClassifier

    model = RandomForestClassifier(n_estimators=64, random_state=42)
    model.fit(history[list(feature_cols)].fillna(0.0), history[hard_col].astype(bool))
    return {"model": model, "model_status": "ok"}


def train_baseline_models(history: pd.DataFrame, feature_cols: Sequence[str]) -> dict[str, Any]:
    return {
        "level": train_level_classifier(history, feature_cols),
        "score": train_score_regressor(history, feature_cols),
        "hard_pass": train_hard_pass_classifier(history, feature_cols),
        "feature_cols": list(feature_cols),
    }


def predict_candidates(models: dict[str, Any], candidate_features: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    output = candidate_features.copy()
    x = output[list(feature_cols)].fillna(0.0) if feature_cols else pd.DataFrame(index=output.index)
    output["p_l1"] = 0.5
    output["predicted_level"] = "L2"
    output["predicted_score"] = 50.0
    output["p_hard_pass"] = 0.5
    output["uncertainty"] = 0.5
    output["model_status"] = "insufficient_data"
    output["unavailable_reason"] = "insufficient_data"
    if models.get("level", {}).get("model_status") == "ok":
        level_model = models["level"]["model"]
        probabilities = level_model.predict_proba(x)
        classes = list(level_model.classes_)
        output["p_l1"] = probabilities[:, classes.index("L1")] if "L1" in classes else 0.0
        output["predicted_level"] = level_model.predict(x)
        output["model_status"] = "ok"
        output["unavailable_reason"] = ""
    if models.get("score", {}).get("model_status") == "ok":
        output["predicted_score"] = models["score"]["model"].predict(x)
    if models.get("hard_pass", {}).get("model_status") == "ok":
        hard_model = models["hard_pass"]["model"]
        probabilities = hard_model.predict_proba(x)
        classes = list(hard_model.classes_)
        output["p_hard_pass"] = probabilities[:, classes.index(True)] if True in classes else 0.0
    output["uncertainty"] = 1.0 - (output["p_l1"].astype(float) - 0.5).abs() * 2.0
    return output
