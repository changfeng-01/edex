from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.product_demo.artifact_collector import ProductDemoArtifacts
from goa_eval.product_demo.schemas import (
    AWAITING_CANDIDATE_GENERATION,
    BEFORE_AFTER_COLUMNS,
    CANDIDATE_COLUMNS,
    CONSTRAINT_COLUMNS,
    RUN_SUMMARY_COLUMNS,
    TABLE_FILES,
)


def write_tables(artifacts: ProductDemoArtifacts, output_dirs: dict[str, Path], case_id: str) -> dict[str, Path]:
    run_summary = build_run_summary_table(artifacts, case_id)
    constraints = build_constraint_table(artifacts)
    candidates = build_candidate_table(artifacts)
    before_after = build_before_after_table(artifacts)
    paths = {
        "run_summary": output_dirs["evaluation"] / TABLE_FILES["run_summary"],
        "constraints": output_dirs["evaluation"] / TABLE_FILES["constraints"],
        "candidates": output_dirs["candidates"] / TABLE_FILES["candidates"],
        "before_after": output_dirs["validation"] / TABLE_FILES["before_after"],
    }
    run_summary.to_csv(paths["run_summary"], index=False)
    constraints.to_csv(paths["constraints"], index=False)
    candidates.to_csv(paths["candidates"], index=False)
    before_after.to_csv(paths["before_after"], index=False)
    return paths


def build_run_summary_table(artifacts: ProductDemoArtifacts, case_id: str) -> pd.DataFrame:
    summary = artifacts.summary
    score = artifacts.score
    manifest = artifacts.manifest
    row = {
        "case_id": case_id,
        "run_id": summary.get("run_id") or manifest.get("run_id") or case_id,
        "overall_status": summary.get("Overall_status") or summary.get("overall_status") or "",
        "overall_score": score.get("overall_score", ""),
        "hard_constraint_passed": score.get("hard_constraint_passed", ""),
        "stage_count": summary.get("stage_count") or summary.get("StageCount") or "",
        "resolved_output_node_count": (manifest.get("thresholds") or {}).get("resolved_output_node_count", ""),
        "validation_status": artifacts.validation_status,
        "candidate_status": artifacts.candidate_status,
        **artifacts.evidence,
    }
    return pd.DataFrame([{column: row.get(column, "") for column in RUN_SUMMARY_COLUMNS}])


def build_constraint_table(artifacts: ProductDemoArtifacts) -> pd.DataFrame:
    constraints = artifacts.score.get("hard_constraints") or {}
    rows = []
    for name, payload in constraints.items():
        passed = payload.get("passed")
        rows.append(
            {
                "constraint": name,
                "status": "pass" if passed is True else "fail" if passed is False else "unknown",
                "current_value": _format_value(payload.get("current_value")),
                "threshold": _format_value(payload.get("threshold")),
                "reason": payload.get("reason", ""),
            }
        )
    if not rows:
        rows.append(
            {
                "constraint": "hard_constraints",
                "status": "missing",
                "current_value": "",
                "threshold": "",
                "reason": "score_summary.json did not include hard_constraints",
            }
        )
    return pd.DataFrame(rows, columns=CONSTRAINT_COLUMNS)


def build_candidate_table(artifacts: ProductDemoArtifacts, *, limit: int = 10) -> pd.DataFrame:
    if artifacts.candidates.empty:
        return pd.DataFrame(
            [
                {
                    "rank": "",
                    "candidate_id": "",
                    "priority": "",
                    "parameter_changes": "",
                    "trigger_metric": "",
                    "strategy": "",
                    "search_score": "",
                    "status": AWAITING_CANDIDATE_GENERATION,
                    "data_source": artifacts.evidence["data_source"],
                    "engineering_validity": artifacts.evidence["engineering_validity"],
                }
            ],
            columns=CANDIDATE_COLUMNS,
        )
    rows = []
    frame = artifacts.candidates.head(limit).copy()
    for index, row in frame.iterrows():
        rows.append(
            {
                "rank": len(rows) + 1,
                "candidate_id": row.get("candidate_id", f"candidate_{index + 1}"),
                "priority": row.get("priority", ""),
                "parameter_changes": _format_parameter_changes(row),
                "trigger_metric": row.get("trigger_metric", ""),
                "strategy": row.get("strategy", ""),
                "search_score": _format_value(row.get("search_score", "")),
                "status": "ready_for_rerun",
                "data_source": row.get("data_source", artifacts.evidence["data_source"]),
                "engineering_validity": row.get("engineering_validity", artifacts.evidence["engineering_validity"]),
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


def build_before_after_table(artifacts: ProductDemoArtifacts) -> pd.DataFrame:
    if artifacts.validation.empty:
        rows = []
        for metric in ["overall_score", "Max_overlap_ratio", "Max_ripple", "Max_voltage_loss"]:
            rows.append(
                {
                    "metric": metric,
                    "before_value": _baseline_value(artifacts, metric),
                    "after_value": "",
                    "delta": "",
                    "status": artifacts.validation_status,
                    "unit": _metric_unit(metric),
                }
            )
        return pd.DataFrame(rows, columns=BEFORE_AFTER_COLUMNS)
    rows = []
    for _, row in artifacts.validation.iterrows():
        metric = row.get("metric") or row.get("name") or row.get("Metric") or "validation_metric"
        before = row.get("before_value", row.get("baseline_value", ""))
        after = row.get("after_value", row.get("candidate_value", ""))
        rows.append(
            {
                "metric": metric,
                "before_value": _format_value(before),
                "after_value": _format_value(after),
                "delta": _format_value(row.get("delta", _delta(before, after))),
                "status": row.get("status", "available"),
                "unit": row.get("unit", _metric_unit(str(metric))),
            }
        )
    return pd.DataFrame(rows, columns=BEFORE_AFTER_COLUMNS)


def _format_parameter_changes(row: pd.Series) -> str:
    changed = row.get("changed_parameters", "")
    params_json = row.get("parameters_json", "")
    if isinstance(params_json, str) and params_json.strip():
        try:
            payload = json.loads(params_json)
            if isinstance(payload, dict):
                return ", ".join(f"{key}: {_format_value(value)}" for key, value in payload.items())
        except json.JSONDecodeError:
            pass
    parameter = row.get("parameter", "")
    value = row.get("candidate_value", "")
    unit = row.get("candidate_unit", "")
    if parameter:
        suffix = f" {unit}" if unit else ""
        return f"{parameter}: {_format_value(value)}{suffix}"
    return str(changed)


def _baseline_value(artifacts: ProductDemoArtifacts, metric: str) -> str:
    if metric == "overall_score":
        return _format_value(artifacts.score.get("overall_score", ""))
    return _format_value(artifacts.summary.get(metric, ""))


def _metric_unit(metric: str) -> str:
    metric_lower = metric.lower()
    if "ratio" in metric_lower or "score" in metric_lower:
        return ""
    if "delay" in metric_lower or "width" in metric_lower or "overlap" in metric_lower:
        return "s"
    if "ripple" in metric_lower or "voltage" in metric_lower or "voh" in metric_lower or "vol" in metric_lower:
        return "V"
    return ""


def _delta(before: Any, after: Any) -> str:
    try:
        return str(float(after) - float(before))
    except (TypeError, ValueError):
        return ""


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        return f"{value:.6g}"
    if isinstance(value, int):
        return str(value)
    if pd.isna(value) if not isinstance(value, (str, list, dict, tuple)) else False:
        return ""
    return str(value)
