"""Strict schema validation for imported PIA simulation results."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def validate_simulation_results(
    results: pd.DataFrame,
    simulation_batch: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate result rows against a simulation batch.

    Returns a cleaned DataFrame plus a machine-readable validation report.
    Raises ValueError for structural problems that would make the imported
    rows unsafe to append to closed-loop history.
    """
    exec_cfg = config.get("simulation_executor", {})
    required_cols = exec_cfg.get(
        "result_required_columns",
        ["candidate_id", "overall_score", "hard_constraint_passed"],
    )
    missing = [col for col in required_cols if col not in results.columns]
    if missing:
        raise ValueError(f"missing required result columns: {missing}")

    cleaned = results.copy()
    report: dict[str, Any] = {
        "row_count": int(len(cleaned)),
        "warnings": [],
        "extra_columns": [],
    }
    if cleaned.empty:
        return cleaned.reset_index(drop=True), report

    if "candidate_id" not in simulation_batch.columns:
        raise ValueError("simulation_batch is missing candidate_id")

    allow_duplicates = bool(exec_cfg.get("allow_duplicate_candidate_ids", False))
    duplicate_mask = cleaned["candidate_id"].duplicated(keep=False)
    if duplicate_mask.any() and not allow_duplicates:
        duplicates = sorted(cleaned.loc[duplicate_mask, "candidate_id"].astype(str).unique())
        raise ValueError(f"duplicate candidate_id rows are not allowed: {duplicates}")

    batch_ids = set(simulation_batch["candidate_id"].astype(str))
    result_ids = set(cleaned["candidate_id"].astype(str))
    unknown_ids = sorted(result_ids - batch_ids)
    if unknown_ids:
        raise ValueError(f"result candidate_id values are not in simulation batch: {unknown_ids}")

    scores = pd.to_numeric(cleaned["overall_score"], errors="coerce")
    if scores.isna().any():
        bad_ids = cleaned.loc[scores.isna(), "candidate_id"].astype(str).tolist()
        raise ValueError(f"overall_score must be numeric for candidate_id values: {bad_ids}")
    cleaned["overall_score"] = scores

    batch_by_id = simulation_batch.set_index(simulation_batch["candidate_id"].astype(str), drop=False)
    parameter_columns = list(config.get("parameter_columns", []))
    for col in parameter_columns:
        if col not in simulation_batch.columns:
            raise ValueError(f"missing parameter column in simulation batch: {col}")
        batch_values = cleaned["candidate_id"].astype(str).map(batch_by_id[col])
        if col not in cleaned.columns:
            cleaned[col] = batch_values
            continue
        result_values = cleaned[col]
        numeric_result = pd.to_numeric(result_values, errors="coerce")
        numeric_batch = pd.to_numeric(batch_values, errors="coerce")
        if numeric_result.notna().all() and numeric_batch.notna().all():
            modified = (numeric_result - numeric_batch).abs() > 1e-9
        else:
            modified = result_values.astype(str) != batch_values.astype(str)
        if modified.any():
            bad_ids = cleaned.loc[modified, "candidate_id"].astype(str).tolist()
            raise ValueError(f"modified parameter column {col} for candidate_id values: {bad_ids}")
        cleaned[col] = batch_values

    known_columns = set(required_cols)
    known_columns.update(parameter_columns)
    known_columns.update(simulation_batch.columns)
    known_columns.update(config.get("metric_columns", []))
    known_columns.update(config.get("hard_constraint_columns", []))
    status_columns = config.get("status_columns", {})
    if isinstance(status_columns, Mapping):
        known_columns.update(status_columns.values())
    extra_columns = [col for col in cleaned.columns if col not in known_columns]
    if extra_columns:
        report["extra_columns"] = extra_columns
        report["warnings"].append({
            "type": "extra_columns_preserved",
            "columns": extra_columns,
        })

    return cleaned.reset_index(drop=True), report
