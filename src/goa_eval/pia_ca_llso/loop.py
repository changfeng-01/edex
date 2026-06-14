from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.selector import select_candidates


def suggest_next_run(history: pd.DataFrame, candidates: pd.DataFrame, config: dict, strategy: str, top_k: int):
    labeled = assign_level_labels(history)
    history_features, feature_report = extract_physics_features(labeled, config.get("physics_features", config))
    candidate_features, candidate_feature_report = extract_physics_features(candidates, config.get("physics_features", config))
    history_joined = pd.concat([labeled.reset_index(drop=True), history_features.reset_index(drop=True)], axis=1)
    candidate_joined = pd.concat([candidates.reset_index(drop=True), candidate_features.reset_index(drop=True)], axis=1)
    result = select_candidates(candidate_joined, history_joined, strategy=strategy, top_k=top_k, config=config)
    result.feature_report = {
        "history": feature_report,
        "candidates": candidate_feature_report,
    }
    return result
