from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


DEFAULT_WEIGHTS = {
    "p_l1": 0.30,
    "predicted_score": 0.20,
    "p_hard_pass": 0.20,
    "uncertainty": 0.10,
    "attention_l1_mass": 0.10,
    "distance": 0.05,
    "diversity": 0.05,
}


def _bounded(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    if numeric > 1.0:
        numeric = numeric / 100.0
    return float(min(max(numeric, 0.0), 1.0))


def compute_acquisition_score(candidate_row: Mapping[str, Any], weights: Mapping[str, float] | None = None) -> tuple[float, dict[str, Any]]:
    active = dict(DEFAULT_WEIGHTS if weights is None else weights)
    diagnostic = "ok"
    attention = candidate_row.get("attention_l1_mass")
    if attention is None or (isinstance(attention, float) and np.isnan(attention)):
        active["attention_l1_mass"] = 0.0
        diagnostic = "attention_unavailable"
    distance_value = candidate_row.get("latent_distance_to_l1", candidate_row.get("physics_distance_to_l1"))
    if distance_value is None or not np.isfinite(float(distance_value)):
        distance_component = 0.5
        if diagnostic == "ok":
            diagnostic = "latent_unavailable"
    else:
        distance_component = 1.0 - _bounded(distance_value)
    total_weight = sum(active.values()) or 1.0
    components = {
        "p_l1": _bounded(candidate_row.get("p_l1", 0.5)),
        "predicted_score": _bounded(candidate_row.get("predicted_score", 50.0)),
        "p_hard_pass": _bounded(candidate_row.get("p_hard_pass", 0.5)),
        "uncertainty": _bounded(candidate_row.get("uncertainty", 0.5)),
        "attention_l1_mass": _bounded(attention, 0.0),
        "distance": distance_component,
        "diversity": _bounded(candidate_row.get("diversity_score", 0.0)),
        "diagnostic_status": diagnostic,
    }
    score = sum((active[key] / total_weight) * components[key] for key in active)
    return float(min(max(score, 0.0), 1.0)), components


def compute_diversity(candidate: pd.Series, selected_candidates: pd.DataFrame, feature_cols: Sequence[str]) -> float:
    if selected_candidates.empty or not feature_cols:
        return 1.0
    distances = []
    for _, row in selected_candidates.iterrows():
        distances.append(float(np.sqrt(sum((float(candidate.get(col, 0.0)) - float(row.get(col, 0.0))) ** 2 for col in feature_cols))))
    return float(min(np.mean(distances), 1.0))


def attach_acquisition_scores(candidates: pd.DataFrame) -> pd.DataFrame:
    output = candidates.copy()
    scores = []
    component_json = []
    statuses = []
    for _, row in output.iterrows():
        score, components = compute_acquisition_score(row)
        scores.append(score)
        component_json.append(json.dumps(components, ensure_ascii=False))
        statuses.append(components["diagnostic_status"])
    output["acquisition_score"] = scores
    output["acquisition_components_json"] = component_json
    output["diagnostic_status"] = statuses
    return output


def explain_acquisition(candidate_row: Mapping[str, Any]) -> str:
    return (
        f"p_l1={candidate_row.get('p_l1', 0):.3g}; "
        f"p_hard_pass={candidate_row.get('p_hard_pass', 0):.3g}; "
        f"predicted_score={candidate_row.get('predicted_score', 0):.3g}; "
        f"acquisition_score={candidate_row.get('acquisition_score', 0):.3g}. "
        "This is a next-run simulation suggestion, not final validation evidence."
    )
