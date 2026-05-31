from __future__ import annotations

from typing import Any

import pandas as pd


DEFAULT_OBJECTIVES = [
    {"name": "Max_overlap_ratio", "direction": "min"},
    {"name": "Max_ripple", "direction": "min"},
    {"name": "Max_voltage_loss", "direction": "min"},
    {"name": "Delay_std", "direction": "min"},
    {"name": "not_evaluable_metric_count", "direction": "min"},
    {"name": "overall_score", "direction": "max"},
    {"name": "hard_constraint_passed", "direction": "max"},
    {"name": "target_passed", "direction": "max"},
    {"name": "LowFreqStable", "direction": "max"},
]

HARD_GATE_FIELDS = {"hard_constraint_passed"}


def pareto_rank(frame: pd.DataFrame, objectives: list[dict[str, str]] | None = None) -> pd.DataFrame:
    objectives = _available_objectives(frame, objectives or DEFAULT_OBJECTIVES)
    ranked = frame.copy()
    if ranked.empty:
        ranked["pareto_rank"] = []
        ranked["pareto_is_front"] = []
        ranked["dominance_count"] = []
        return ranked
    if not objectives:
        ranked["pareto_rank"] = 1
        ranked["pareto_is_front"] = True
        ranked["dominance_count"] = 0
        ranked["candidate_style"] = classify_candidate_style(ranked)
        return ranked

    rows = [row.to_dict() for _, row in ranked.iterrows()]
    dominance_counts = []
    for index, row in enumerate(rows):
        dominance_counts.append(sum(1 for other_index, other in enumerate(rows) if index != other_index and is_dominated(row, other, objectives)))

    remaining = set(range(len(rows)))
    ranks: dict[int, int] = {}
    current_rank = 1
    while remaining:
        front = [
            index
            for index in sorted(remaining)
            if not any(index != other and is_dominated(rows[index], rows[other], objectives) for other in remaining)
        ]
        if not front:
            front = sorted(remaining)
        for index in front:
            ranks[index] = current_rank
            remaining.remove(index)
        current_rank += 1

    ranked["dominance_count"] = dominance_counts
    ranked["pareto_rank"] = [ranks[index] for index in range(len(rows))]
    ranked["pareto_is_front"] = pd.Series([ranks[index] == 1 for index in range(len(rows))], dtype=object)
    ranked["candidate_style"] = classify_candidate_style(ranked)
    return ranked


def is_dominated(a: dict[str, Any] | pd.Series, b: dict[str, Any] | pd.Series, objectives: list[dict[str, str]] | None = None) -> bool:
    objectives = objectives or DEFAULT_OBJECTIVES
    for field in HARD_GATE_FIELDS:
        if any(objective.get("name") == field for objective in objectives):
            a_gate = _as_bool(_get(a, field))
            b_gate = _as_bool(_get(b, field))
            if a_gate is False and b_gate is True:
                return True
            if a_gate is True and b_gate is False:
                return False

    comparable = False
    strictly_better = False
    for objective in objectives:
        name = str(objective.get("name", ""))
        direction = str(objective.get("direction", "max"))
        a_value = _objective_value(_get(a, name))
        b_value = _objective_value(_get(b, name))
        if a_value is None or b_value is None:
            continue
        comparable = True
        if direction == "min":
            if b_value > a_value:
                return False
            if b_value < a_value:
                strictly_better = True
        else:
            if b_value < a_value:
                return False
            if b_value > a_value:
                strictly_better = True
    return comparable and strictly_better


def select_knee_points(frame: pd.DataFrame, *, max_points: int = 3) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    ranked = frame if "pareto_rank" in frame.columns else pareto_rank(frame)
    front = ranked[ranked["pareto_rank"] == 1].copy()
    if front.empty:
        return ranked.head(max_points).copy()
    score_columns = [
        column
        for column in ["overall_score", "predicted_overall_score", "Max_overlap_ratio", "predicted_Max_overlap_ratio", "Max_ripple", "predicted_Max_ripple"]
        if column in front.columns
    ]
    if not score_columns:
        return front.head(max_points).copy()
    normalized = pd.DataFrame(index=front.index)
    for column in score_columns:
        values = pd.to_numeric(front[column], errors="coerce")
        spread = values.max() - values.min()
        if pd.isna(spread) or spread == 0:
            normalized[column] = 0.5
        elif "score" in column:
            normalized[column] = (values - values.min()) / spread
        else:
            normalized[column] = 1.0 - ((values - values.min()) / spread)
    front["_knee_score"] = normalized.mean(axis=1)
    return front.sort_values(["_knee_score", "candidate_id"], ascending=[False, True], kind="mergesort").head(max_points).drop(columns=["_knee_score"])


def classify_candidate_style(frame: pd.DataFrame | pd.Series) -> pd.Series | str:
    if isinstance(frame, pd.Series):
        return _classify_row(frame.to_dict())
    return pd.Series([_classify_row(row.to_dict()) for _, row in frame.iterrows()], index=frame.index, dtype=object)


def _classify_row(row: dict[str, Any]) -> str:
    source = str(row.get("candidate_source", "") or "").lower()
    operator = str(row.get("repair_operator", "") or "").lower()
    mutation = _objective_value(row.get("mutation_strength")) or 0.0
    hard_passed = _as_bool(row.get("predicted_hard_constraint_passed", row.get("hard_constraint_passed")))
    if source == "repair" or operator:
        if "conservative" in operator or mutation <= 0.12:
            return "repair_first"
        return "balanced"
    if source == "exploration":
        return "exploratory"
    if hard_passed is False or mutation >= 0.3:
        return "aggressive"
    if mutation <= 0.1:
        return "conservative"
    return "balanced"


def _available_objectives(frame: pd.DataFrame, objectives: list[dict[str, str]]) -> list[dict[str, str]]:
    return [objective for objective in objectives if str(objective.get("name", "")) in frame.columns]


def _objective_value(value: Any) -> float | None:
    if value is True:
        return 1.0
    if value is False:
        return 0.0
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return 1.0 if value.strip().lower() == "true" else 0.0
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is True or str(value).strip().lower() == "true":
        return True
    if value is False or str(value).strip().lower() == "false":
        return False
    return None


def _get(row: dict[str, Any] | pd.Series, key: str) -> Any:
    if isinstance(row, pd.Series):
        return row.get(key)
    return row.get(key)
