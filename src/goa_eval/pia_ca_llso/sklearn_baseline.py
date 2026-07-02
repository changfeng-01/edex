from __future__ import annotations

from typing import Any, Sequence

import numpy as np
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
    output["level_entropy_uncertainty"] = 0.5
    output["hard_pass_entropy_uncertainty"] = 0.5
    output["predicted_score_tree_std"] = 0.0
    output["score_tree_std_uncertainty"] = 0.5
    output["model_status"] = "insufficient_data"
    output["unavailable_reason"] = "insufficient_data"
    if models.get("level", {}).get("model_status") == "ok":
        level_model = models["level"]["model"]
        probabilities = level_model.predict_proba(x)
        classes = list(level_model.classes_)
        output["p_l1"] = probabilities[:, classes.index("L1")] if "L1" in classes else 0.0
        output["predicted_level"] = level_model.predict(x)
        output["level_entropy_uncertainty"] = _normalized_entropy(probabilities)
        output["model_status"] = "ok"
        output["unavailable_reason"] = ""
    if models.get("score", {}).get("model_status") == "ok":
        score_model = models["score"]["model"]
        output["predicted_score"] = score_model.predict(x)
        output["predicted_score_tree_std"] = _tree_prediction_std(score_model, x)
        output["score_tree_std_uncertainty"] = _normalize_series(output["predicted_score_tree_std"])
    if models.get("hard_pass", {}).get("model_status") == "ok":
        hard_model = models["hard_pass"]["model"]
        probabilities = hard_model.predict_proba(x)
        classes = list(hard_model.classes_)
        output["p_hard_pass"] = probabilities[:, classes.index(True)] if True in classes else 0.0
        output["hard_pass_entropy_uncertainty"] = _normalized_binary_entropy(output["p_hard_pass"].astype(float))
    output["uncertainty"] = (
        0.40 * output["level_entropy_uncertainty"].astype(float)
        + 0.30 * output["hard_pass_entropy_uncertainty"].astype(float)
        + 0.30 * output["score_tree_std_uncertainty"].astype(float)
    ).clip(0.0, 1.0)
    return output


def _normalized_entropy(probabilities: np.ndarray) -> np.ndarray:
    if probabilities.size == 0:
        return np.array([], dtype=float)
    clipped = np.clip(probabilities.astype(float), 1e-12, 1.0)
    entropy = -(clipped * np.log(clipped)).sum(axis=1)
    normalizer = np.log(max(clipped.shape[1], 2))
    return np.clip(entropy / normalizer, 0.0, 1.0)


def _normalized_binary_entropy(probabilities: pd.Series) -> pd.Series:
    p = probabilities.astype(float).clip(1e-12, 1.0 - 1e-12)
    entropy = -(p * np.log(p) + (1.0 - p) * np.log(1.0 - p))
    return (entropy / np.log(2.0)).clip(0.0, 1.0)


def _tree_prediction_std(model: Any, x: pd.DataFrame) -> np.ndarray:
    estimators = getattr(model, "estimators_", None)
    if not estimators:
        return np.zeros(len(x), dtype=float)
    values = x.to_numpy() if hasattr(x, "to_numpy") else x
    predictions = np.vstack([estimator.predict(values) for estimator in estimators])
    return predictions.std(axis=0)


def _normalize_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    max_value = float(numeric.max()) if not numeric.empty else 0.0
    if max_value <= 0.0:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return (numeric / max_value).clip(0.0, 1.0)
