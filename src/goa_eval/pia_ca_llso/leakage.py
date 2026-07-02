"""Shared leakage checks for formal PIA validation."""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

FORMAL_RESULT_LEAKAGE_COLUMNS = {
    "overall_score",
    "objective_score",
    "target_hit",
    "best_score",
    "hard_constraint_passed",
    "simulations_to_target",
    "convergence_auc",
    "budget_index",
    "result_status",
}


def find_result_leakage_columns(columns: Iterable[str]) -> list[str]:
    return sorted(str(column) for column in columns if str(column) in FORMAL_RESULT_LEAKAGE_COLUMNS)


def assert_no_result_leakage(candidates: pd.DataFrame, context: str = "candidate pool") -> None:
    leakage = find_result_leakage_columns(candidates.columns)
    if leakage:
        raise ValueError(f"{context} contains result leakage columns: {', '.join(leakage)}")


def leakage_audit_rows(scenario_id: str, candidates: pd.DataFrame) -> list[dict[str, object]]:
    leakage = find_result_leakage_columns(candidates.columns)
    return [
        {
            "scenario_id": scenario_id,
            "leakage_check_passed": not leakage,
            "leakage_columns": ",".join(leakage),
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        }
    ]
