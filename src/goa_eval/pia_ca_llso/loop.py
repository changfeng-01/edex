from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.candidate_generator import generate_constraint_repair_candidates
from goa_eval.pia_ca_llso.evaluation_scheduler import attach_evaluation_schedule
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.physics_distance import FORBIDDEN_DISTANCE_COLUMNS
from goa_eval.pia_ca_llso.selector import ACTIVE_ACQUISITION_STRATEGY, CLASSIFIER_REQUIRED_STRATEGIES, select_candidates
from goa_eval.pia_ca_llso.sklearn_baseline import predict_candidates, train_baseline_models


def suggest_next_run(history: pd.DataFrame, candidates: pd.DataFrame, config: dict, strategy: str, top_k: int):
    labeled = assign_level_labels(history)
    history_features, feature_report = extract_physics_features(labeled, config.get("physics_features", config))
    candidate_features, candidate_feature_report = extract_physics_features(candidates, config.get("physics_features", config))
    history_joined = pd.concat([labeled.reset_index(drop=True), history_features.reset_index(drop=True)], axis=1)
    candidate_joined = pd.concat([candidates.reset_index(drop=True), candidate_features.reset_index(drop=True)], axis=1)
    # Drop duplicate columns that may arise from overlapping feature names
    history_joined = history_joined.loc[:, ~history_joined.columns.duplicated()]
    candidate_joined = candidate_joined.loc[:, ~candidate_joined.columns.duplicated()]
    repairs = generate_constraint_repair_candidates(history_joined, candidate_joined, config)
    repair_report = {"enabled": config.get("repair_candidates", {}).get("enabled", True), "generated_count": int(len(repairs))}
    if not repairs.empty:
        repair_features, repair_feature_report = extract_physics_features(repairs, config.get("physics_features", config))
        repair_joined = repairs.copy()
        for column in repair_features.columns:
            repair_joined[column] = repair_features[column].values
        candidate_joined = pd.concat([candidate_joined, repair_joined], ignore_index=True, sort=False)
        repair_report["feature_report"] = repair_feature_report
    classifier_enabled = _classifier_predictions_enabled(strategy, config)
    classifier_report = {"enabled": classifier_enabled, "model_status": "not_used"}
    if classifier_enabled:
        feature_cols = _shared_model_features(candidate_joined, history_joined)
        models = train_baseline_models(history_joined, feature_cols)
        candidate_joined = predict_candidates(models, candidate_joined, feature_cols)
        classifier_report = {
            "enabled": True,
            "model_status": _classifier_status(models),
            "feature_count": int(len(feature_cols)),
        }
    result = select_candidates(candidate_joined, history_joined, strategy=strategy, top_k=top_k, config=config)
    result.selected_candidates, scheduler_report = attach_evaluation_schedule(result.selected_candidates, config)
    result.feature_report = {
        "history": feature_report,
        "candidates": candidate_feature_report,
        "repair_candidates": repair_report,
        "classifier_level_hybrid": classifier_report,
        "evaluation_scheduler": scheduler_report,
    }
    return result


def _shared_model_features(candidates: pd.DataFrame, history: pd.DataFrame) -> list[str]:
    return [
        column
        for column in candidates.columns
        if column in history.columns
        and column not in FORBIDDEN_DISTANCE_COLUMNS
        and pd.api.types.is_numeric_dtype(candidates[column])
        and pd.api.types.is_numeric_dtype(history[column])
    ]


def _classifier_status(models: dict) -> str:
    statuses = [str(value.get("model_status")) for value in models.values() if isinstance(value, dict)]
    return "ok" if "ok" in statuses else "insufficient_data"


def _classifier_predictions_enabled(strategy: str, config: dict) -> bool:
    if strategy not in CLASSIFIER_REQUIRED_STRATEGIES:
        return False
    if strategy == ACTIVE_ACQUISITION_STRATEGY:
        return config.get("classifier_level_hybrid", {}).get("enabled", True) is not False
    return True
