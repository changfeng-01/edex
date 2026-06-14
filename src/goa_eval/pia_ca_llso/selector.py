from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from goa_eval.pia_ca_llso.acquisition import attach_acquisition_scores, compute_diversity, explain_acquisition
from goa_eval.pia_ca_llso.physics_distance import (
    FORBIDDEN_DISTANCE_COLUMNS,
    compute_capm_distance,
    distance_to_l1_physics,
    normalize_distance,
    physics_geodesic_distance_to_l1,
)
from goa_eval.pia_ca_llso.raw_distance import select_by_raw_distance
from goa_eval.pia_ca_llso.schema import SelectionResult


ROLES = ["exploitation_best", "l1_center", "boundary_learning", "diversity_exploration"]


def select_candidates(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    strategy: str = "pia_physics_distance",
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> SelectionResult:
    if strategy == "random":
        selected = select_random(candidates, top_k)
        scored = selected.copy()
    elif strategy == "ca_llso_raw_distance":
        scored = select_raw_distance(candidates, history, top_k)
        selected = scored.head(top_k)
    elif strategy in {"pia_physics_distance", "pia_latent_metric", "pia_full_attention"}:
        scored = select_physics_distance(candidates, history, top_k)
        selected = scored.head(top_k)
    elif strategy == "pia_capm_distance":
        scored = select_capm_distance(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    else:
        raise ValueError(f"Unknown PIA selection strategy: {strategy}")
    selected = assign_candidate_roles(selected.reset_index(drop=True))
    selected["selection_reason"] = [explain_acquisition(row) for row in selected.to_dict("records")]
    return SelectionResult(
        selected_candidates=selected,
        all_candidates=scored,
        model_report={"strategy": strategy, "selected_count": int(len(selected))},
        explanation_report=build_selection_report(selected, strategy),
    )


def select_random(candidates: pd.DataFrame, top_k: int = 4, seed: int = 42) -> pd.DataFrame:
    return candidates.sample(n=min(top_k, len(candidates)), random_state=seed).reset_index(drop=True)


def select_raw_distance(candidates: pd.DataFrame, history: pd.DataFrame, top_k: int = 4) -> pd.DataFrame:
    numeric = [col for col in candidates.columns if col in history.columns and pd.api.types.is_numeric_dtype(candidates[col])]
    selected = select_by_raw_distance(candidates, history, top_k=len(candidates), parameter_names=numeric)
    selected = attach_acquisition_scores(selected)
    return selected.sort_values(["acquisition_score", "raw_distance_to_l1"], ascending=[False, True]).head(top_k)


def select_physics_distance(candidates: pd.DataFrame, history: pd.DataFrame, top_k: int = 4) -> pd.DataFrame:
    output = candidates.copy()
    l1 = history[history.get("level_label", "") == "L1"] if "level_label" in history.columns else pd.DataFrame()
    feature_cols = _shared_numeric_columns(output, history)
    distances = []
    for _, row in output.iterrows():
        result = distance_to_l1_physics(row[feature_cols], l1[feature_cols] if not l1.empty else l1)
        distances.append(result["distance"] if result["distance"] is not None else float("inf"))
    output["physics_distance_to_l1"] = normalize_distance(distances)
    output = _attach_diversity(output, feature_cols)
    output = attach_acquisition_scores(output)
    return output.sort_values("acquisition_score", ascending=False).head(top_k)


def select_capm_distance(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    output = candidates.copy()
    feature_cols = _shared_numeric_columns(output, history)
    scored = physics_geodesic_distance_to_l1(
        output[["candidate_id", *feature_cols]] if "candidate_id" in output else output[feature_cols],
        history[feature_cols + _history_label_columns(history)],
        config=config,
    )
    for column in ["capm_distance_to_l1", "capm_geodesic_distance_to_l1", "capm_barrier_score", "capm_missing_penalty", "capm_status"]:
        output[column] = scored[column].values
    output["capm_distance_to_l1_normalized"] = normalize_distance(output["capm_geodesic_distance_to_l1"].tolist())
    # Use CAPM distance for diversity to align with physics-manifold semantics
    def _capm_distance_fn(a: pd.Series, b: pd.Series) -> float:
        result = compute_capm_distance(a, b, config=config)
        return float(result.get("distance", float("inf")))

    output = _attach_diversity(output, feature_cols, distance_fn=_capm_distance_fn)
    output["capm_hard_risk_passed"] = pd.Series(
        [bool(value <= 0.0) for value in output["capm_barrier_score"].astype(float)],
        index=output.index,
        dtype="object",
    )
    output["acquisition_score"] = (
        0.45 * (1.0 - output["capm_distance_to_l1_normalized"].astype(float))
        + 0.25 * output["diversity_score"].astype(float)
        + 0.25 * output["capm_hard_risk_passed"].astype(float)
        + 0.05 * (1.0 - output["capm_missing_penalty"].astype(float).clip(0.0, 1.0))
    ).clip(0.0, 1.0)
    output["acquisition_components_json"] = [
        json.dumps(
            {
                "distance": float(1.0 - row["capm_distance_to_l1_normalized"]),
                "diversity": float(row["diversity_score"]),
                "hard_mask": bool(row["capm_hard_risk_passed"]),
                "missing_feature_confidence": float(1.0 - min(max(row["capm_missing_penalty"], 0.0), 1.0)),
                "diagnostic_status": "capm_physics_manifold_no_training",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for _, row in output.iterrows()
    ]
    output["diagnostic_status"] = "capm_physics_manifold_no_training"
    return output.sort_values(
        ["capm_hard_risk_passed", "capm_distance_to_l1_normalized", "diversity_score", "candidate_id"],
        ascending=[False, True, False, True],
    ).head(top_k)


def assign_candidate_roles(selected: pd.DataFrame) -> pd.DataFrame:
    output = selected.copy()
    output["selected_rank"] = range(1, len(output) + 1)
    output["candidate_role"] = [ROLES[idx] if idx < len(ROLES) else "additional_candidate" for idx in range(len(output))]
    return output


def build_selection_report(selected: pd.DataFrame, strategy: str = "pia_physics_distance") -> dict[str, object]:
    return {
        "strategy": strategy,
        "selected_count": int(len(selected)),
        "candidate_ids": list(selected.get("candidate_id", pd.Series(dtype="object"))),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "claim_boundary": "next-run simulation suggestions",
    }


def _shared_numeric_columns(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    return [
        col
        for col in left.columns
        if col in right.columns and col not in FORBIDDEN_DISTANCE_COLUMNS and pd.api.types.is_numeric_dtype(left[col])
    ]


def _history_label_columns(history: pd.DataFrame) -> list[str]:
    return [column for column in ["sample_id", "level_label"] if column in history.columns]


def _attach_diversity(
    frame: pd.DataFrame,
    feature_cols: Sequence[str],
    distance_fn: Callable[[pd.Series, pd.Series], float] | None = None,
) -> pd.DataFrame:
    output = frame.copy()
    selected = pd.DataFrame()
    scores = []
    for _, row in output.iterrows():
        score = compute_diversity(row, selected, feature_cols, distance_fn=distance_fn)
        scores.append(score)
        selected = pd.concat([selected, row.to_frame().T], ignore_index=True)
    output["diversity_score"] = scores
    return output
