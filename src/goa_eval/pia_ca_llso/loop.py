from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.candidate_generator import generate_constraint_repair_candidates
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.selector import select_candidates


def suggest_next_run(history: pd.DataFrame, candidates: pd.DataFrame, config: dict, strategy: str, top_k: int):
    labeled = assign_level_labels(history)
    history_features, feature_report = extract_physics_features(labeled, config.get("physics_features", config))
    candidate_features, candidate_feature_report = extract_physics_features(candidates, config.get("physics_features", config))
    history_joined = pd.concat([labeled.reset_index(drop=True), history_features.reset_index(drop=True)], axis=1)
    candidate_joined = pd.concat([candidates.reset_index(drop=True), candidate_features.reset_index(drop=True)], axis=1)
    repairs = generate_constraint_repair_candidates(history_joined, candidate_joined, config)
    repair_report = {"enabled": config.get("repair_candidates", {}).get("enabled", True), "generated_count": int(len(repairs))}
    if not repairs.empty:
        repair_features, repair_feature_report = extract_physics_features(repairs, config.get("physics_features", config))
        repair_joined = repairs.copy()
        for column in repair_features.columns:
            repair_joined[column] = repair_features[column].values
        candidate_joined = pd.concat([candidate_joined, repair_joined], ignore_index=True, sort=False)
        repair_report["feature_report"] = repair_feature_report
    result = select_candidates(candidate_joined, history_joined, strategy=strategy, top_k=top_k, config=config)
    result.feature_report = {
        "history": feature_report,
        "candidates": candidate_feature_report,
        "repair_candidates": repair_report,
    }
    return result
