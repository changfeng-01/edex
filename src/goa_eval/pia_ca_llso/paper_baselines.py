from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.physics_distance import FORBIDDEN_DISTANCE_COLUMNS
from goa_eval.pia_ca_llso.leakage import FORMAL_RESULT_LEAKAGE_COLUMNS
from goa_eval.pia_ca_llso.sklearn_baseline import predict_candidates, train_baseline_models


PAPER_BASELINE_STRATEGIES = (
    "paper_ca_llso",
    "paper_adaptive_constraint_eval",
    "paper_distributed_multi_constraint",
)

FIDELITY_LEVEL = "faithful_goa_reimplementation"
CLAIM_BOUNDARY = "not_original_paper_benchmark_reproduction"

RESULT_LEAKAGE_COLUMNS = {
    *FORBIDDEN_DISTANCE_COLUMNS,
    *FORMAL_RESULT_LEAKAGE_COLUMNS,
    "real_score",
    "target_hit",
    "simulation_result",
    "waveform_metric",
    "waveform_quality",
    "feasible_score",
}

PIA_EXCLUSIVE_COLUMNS = {
    "capm_distance_to_l1",
    "capm_geodesic_distance_to_l1",
    "capm_barrier_score",
    "capm_missing_penalty",
    "capm_hard_risk_passed",
    "adaptive_capm_weights_json",
    "adaptive_acquisition_weights_json",
    "classifier_hybrid_score",
    "classifier_components_json",
    "constraint_ledger_json",
    "constraint_ledger_repair_json",
    "source",
    "simulation_window",
    "constraint_eval_plan_json",
    "evaluation_state",
    "evidence_state",
}


def build_reproduction_cards() -> list[dict[str, Any]]:
    return [
        {
            "paper_id": "paper_ca_llso",
            "reproduced_components": [
                "classifier-assisted level ranking",
                "L1-oriented learning over a shared candidate pool",
                "LLSO-style preference for high-level and uncertain candidates",
            ],
            "omitted_components": [
                "original paper benchmark suite",
                "paper-specific population update constants not observable in the GOA CSV protocol",
                "PIA CAPM, constraint-ledger repair, and evaluation scheduler",
            ],
            "parameter_mapping": {
                "level": "level_label",
                "objective": "overall_score from history only",
                "candidate_pool": "shared GOA candidate CSV before simulation evidence import",
            },
            "fidelity_level": FIDELITY_LEVEL,
            "claim_boundary": CLAIM_BOUNDARY,
        },
        {
            "paper_id": "paper_adaptive_constraint_eval",
            "reproduced_components": [
                "constraint-first candidate ordering",
                "uncertainty-aware partial constraint priority",
                "shared budget accounting by imported simulation rows",
            ],
            "omitted_components": [
                "original surrogate model architecture",
                "original benchmark constraints",
                "PIA constraint-ledger repair actions",
            ],
            "parameter_mapping": {
                "constraint_uncertainty": "distance to normalized feasibility boundary",
                "partial_evaluation": "constraint_eval_priority_json",
                "objective": "not used before simulation",
            },
            "fidelity_level": FIDELITY_LEVEL,
            "claim_boundary": CLAIM_BOUNDARY,
        },
        {
            "paper_id": "paper_distributed_multi_constraint",
            "reproduced_components": [
                "per-constraint scoring",
                "distributed-style feasibility aggregation",
                "multi-constraint rank before objective evidence",
            ],
            "omitted_components": [
                "distributed compute topology",
                "original paper benchmark suite",
                "PIA adaptive CAPM weight learning",
            ],
            "parameter_mapping": {
                "local_constraint_models": "one score per available GOA constraint proxy",
                "global_feasibility_rank": "mean and minimum normalized constraint score",
                "objective": "not used before simulation",
            },
            "fidelity_level": FIDELITY_LEVEL,
            "claim_boundary": CLAIM_BOUNDARY,
        },
    ]


def paper_baseline_names() -> list[str]:
    return list(PAPER_BASELINE_STRATEGIES)


def get_reproduction_card(strategy: str) -> dict[str, Any]:
    cards = {card["paper_id"]: card for card in build_reproduction_cards()}
    if strategy not in cards:
        raise ValueError(f"Unknown paper baseline strategy: {strategy}")
    return cards[strategy]


def sanitize_candidate_pool(candidates: pd.DataFrame) -> pd.DataFrame:
    """Remove columns that may contain post-simulation evidence before ranking."""
    drop_columns = [column for column in candidates.columns if _is_leakage_or_pia_column(column)]
    return candidates.drop(columns=drop_columns, errors="ignore")


def select_paper_baseline(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    strategy: str,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    if strategy not in PAPER_BASELINE_STRATEGIES:
        raise ValueError(f"Unknown paper baseline strategy: {strategy}")
    _reject_result_leakage(candidates)
    feature_cols = _shared_safe_numeric_columns(candidates, history)
    if strategy == "paper_ca_llso":
        selected = _rank_ca_llso(candidates, history, feature_cols)
    elif strategy == "paper_adaptive_constraint_eval":
        selected = _rank_adaptive_constraint_eval(candidates, history, feature_cols)
    else:
        selected = _rank_distributed_multi_constraint(candidates, history, feature_cols)
    selected = selected.sort_values(["acquisition_score", "candidate_id"], ascending=[False, True]).head(top_k).reset_index(drop=True)
    card = get_reproduction_card(strategy)
    selected["paper_baseline_strategy"] = strategy
    selected["reproduction_card_json"] = json.dumps(card, ensure_ascii=False, sort_keys=True)
    selected["diagnostic_status"] = strategy
    selected["data_source"] = "real_simulation_csv"
    selected["engineering_validity"] = "simulation_only"
    selected["must_resimulate"] = True
    return selected


def _rank_ca_llso(candidates: pd.DataFrame, history: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    output = predict_candidates(train_baseline_models(history, feature_cols), candidates, feature_cols)
    diversity = _diversity_scores(output, feature_cols)
    p_l1 = output["p_l1"].map(_bounded)
    p_hard = output["p_hard_pass"].map(_bounded)
    uncertainty = output["uncertainty"].map(_bounded)
    predicted_score = output["predicted_score"].map(_bounded)
    output["ca_llso_level_score"] = (0.45 * p_l1 + 0.20 * p_hard + 0.20 * uncertainty + 0.15 * predicted_score).clip(0.0, 1.0)
    output["diversity_score"] = diversity
    output["acquisition_score"] = (0.85 * output["ca_llso_level_score"] + 0.15 * output["diversity_score"]).clip(0.0, 1.0)
    output["paper_components_json"] = [
        json.dumps(
            {
                "p_l1": float(row["p_l1"]),
                "p_hard_pass": float(row["p_hard_pass"]),
                "uncertainty": float(row["uncertainty"]),
                "predicted_score": float(_bounded(row["predicted_score"])),
                "diversity_score": float(row["diversity_score"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for _, row in output.iterrows()
    ]
    return output


def _rank_adaptive_constraint_eval(candidates: pd.DataFrame, history: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    output = candidates.copy()
    scores = _constraint_score_frame(output, history, feature_cols)
    output["constraint_feasibility_score"] = scores["mean_feasibility"]
    output["constraint_uncertainty"] = 1.0 - (scores["mean_feasibility"] - 0.5).abs().clip(0.0, 0.5) * 2.0
    output["diversity_score"] = _diversity_scores(output, feature_cols)
    output["adaptive_constraint_score"] = (
        0.45 * output["constraint_feasibility_score"]
        + 0.35 * output["constraint_uncertainty"]
        + 0.20 * output["diversity_score"]
    ).clip(0.0, 1.0)
    output["acquisition_score"] = output["adaptive_constraint_score"]
    output["constraint_eval_priority_json"] = [
        json.dumps(plan, ensure_ascii=False, sort_keys=True) for plan in scores["plans"]
    ]
    return output


def _rank_distributed_multi_constraint(candidates: pd.DataFrame, history: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    output = candidates.copy()
    scores = _constraint_score_frame(output, history, feature_cols)
    output["distributed_constraint_mean_score"] = scores["mean_feasibility"]
    output["distributed_constraint_min_score"] = scores["min_feasibility"]
    output["diversity_score"] = _diversity_scores(output, feature_cols)
    output["distributed_constraint_score"] = (
        0.55 * output["distributed_constraint_mean_score"]
        + 0.25 * output["distributed_constraint_min_score"]
        + 0.20 * output["diversity_score"]
    ).clip(0.0, 1.0)
    output["acquisition_score"] = output["distributed_constraint_score"]
    output["distributed_constraint_components_json"] = [
        json.dumps(components, ensure_ascii=False, sort_keys=True) for components in scores["components"]
    ]
    return output


def _constraint_score_frame(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    feature_cols: Sequence[str],
) -> dict[str, Any]:
    constraint_cols = [column for column in feature_cols if _looks_like_constraint_proxy(column)]
    if not constraint_cols:
        constraint_cols = list(feature_cols)
    means = []
    mins = []
    components = []
    plans = []
    for _, row in candidates.iterrows():
        row_components = {}
        for column in constraint_cols:
            value = _number(row.get(column), 0.0)
            series = pd.to_numeric(history[column], errors="coerce") if column in history.columns else pd.Series(dtype=float)
            normalized = _normalize_against_history(value, series)
            if _lower_is_better(column):
                score = 1.0 - normalized
            else:
                score = normalized
            row_components[column] = float(min(max(score, 0.0), 1.0))
        if not row_components:
            row_components["overall_candidate"] = 0.5
        ordered = sorted(row_components.items(), key=lambda item: item[1])
        means.append(float(np.mean(list(row_components.values()))))
        mins.append(float(min(row_components.values())))
        components.append(row_components)
        plans.append(
            {
                "priority_constraints": [{"feature": name, "score": score} for name, score in ordered[:3]],
                "claim_boundary": "pre-simulation constraint scheduling baseline",
            }
        )
    return {
        "mean_feasibility": pd.Series(means, index=candidates.index, dtype=float),
        "min_feasibility": pd.Series(mins, index=candidates.index, dtype=float),
        "components": components,
        "plans": plans,
    }


def _reject_result_leakage(candidates: pd.DataFrame) -> None:
    blocked = [column for column in candidates.columns if column in RESULT_LEAKAGE_COLUMNS and column not in {"candidate_id"}]
    if blocked:
        raise ValueError(f"paper baseline ranking received result leakage columns: {', '.join(sorted(blocked))}")


def _shared_safe_numeric_columns(candidates: pd.DataFrame, history: pd.DataFrame) -> list[str]:
    return [
        column
        for column in candidates.columns
        if column in history.columns
        and not _is_leakage_or_pia_column(column)
        and pd.api.types.is_numeric_dtype(candidates[column])
        and pd.api.types.is_numeric_dtype(history[column])
    ]


def _is_leakage_or_pia_column(column: str) -> bool:
    if column == "candidate_id":
        return False
    return column in RESULT_LEAKAGE_COLUMNS or column in PIA_EXCLUSIVE_COLUMNS


def _looks_like_constraint_proxy(column: str) -> bool:
    lowered = column.lower()
    return any(token in lowered for token in ("constraint", "margin", "ron", "ratio", "slew", "cboot", "cload", "vgh", "vgl"))


def _lower_is_better(column: str) -> bool:
    lowered = column.lower()
    return any(token in lowered for token in ("risk", "violation", "ron", "slew", "rise_time", "fall_time", "cload"))


def _normalize_against_history(value: float, history_values: pd.Series) -> float:
    finite = pd.to_numeric(history_values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return 0.5
    low = float(finite.min())
    high = float(finite.max())
    if abs(high - low) < 1e-12:
        return 0.5
    return float(min(max((value - low) / (high - low), 0.0), 1.0))


def _diversity_scores(frame: pd.DataFrame, feature_cols: Sequence[str]) -> pd.Series:
    if not feature_cols or frame.empty:
        return pd.Series(0.5, index=frame.index, dtype=float)
    matrix = frame[list(feature_cols)].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    scores = []
    selected: list[np.ndarray] = []
    for row in matrix:
        if not selected:
            scores.append(1.0)
        else:
            distances = [float(np.linalg.norm(row - previous)) for previous in selected]
            scores.append(min(distances))
        selected.append(row)
    max_score = max(scores) if scores else 1.0
    if max_score <= 0:
        return pd.Series(0.5, index=frame.index, dtype=float)
    return pd.Series([float(score / max_score) for score in scores], index=frame.index, dtype=float)


def _bounded(value: Any, default: float = 0.0) -> float:
    numeric = _number(value, default)
    if numeric > 1.0:
        numeric = numeric / 100.0
    return float(min(max(numeric, 0.0), 1.0))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(numeric):
        return default
    return numeric
