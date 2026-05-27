from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.optimizer import propose_candidates, rank_candidates
from goa_eval.multi_agent.schemas import ToolResult
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


BAD_CELL_STRINGS = {"none", "nan", "missing", "not_evaluable", "not_evaluable_with_current_waveform"}


def inspect_task_inputs(inputs: dict[str, Any]) -> ToolResult:
    summary: dict[str, Any] = {}
    missing: list[str] = []
    for key, value in (inputs or {}).items():
        path = Path(str(value))
        exists = path.exists()
        summary[key] = {"path": str(path), "exists": exists, "kind": _input_kind(key)}
        if not exists:
            missing.append(key)
    status = "warning" if missing else "pass"
    return ToolResult("inspect_task_inputs", status, {"available_inputs": summary, "missing_inputs": missing}, warnings=missing)


def inspect_leaderboard(leaderboard_path: str | Path) -> ToolResult:
    path = Path(leaderboard_path)
    if not path.exists():
        return ToolResult("inspect_leaderboard", "fail", {"path": str(path)}, failures=[f"missing leaderboard: {path}"])
    frame = pd.read_csv(path)
    if frame.empty:
        return ToolResult("inspect_leaderboard", "warning", {"path": str(path), "row_count": 0}, warnings=["leaderboard is empty"])
    sort_column = "overall_score" if "overall_score" in frame.columns else None
    best = frame.sort_values(sort_column, ascending=False, na_position="last").iloc[0] if sort_column else frame.iloc[0]
    best_dict = _jsonable_row(best.to_dict())
    candidate_id = best_dict.get("candidate_id") or best_dict.get("run_id") or best_dict.get("parameter_set_id")
    best_dict["candidate_id"] = candidate_id
    key_metrics = {
        key: best_dict.get(key)
        for key in [
            "overall_score",
            "hard_constraint_passed",
            "delay",
            "Delay",
            "rise_time",
            "fall_time",
            "Max_overlap_ratio",
            "Max_ripple",
            "FalseTriggerCount",
        ]
        if key in best_dict
    }
    return ToolResult(
        "inspect_leaderboard",
        "pass",
        {
            "path": str(path),
            "row_count": int(len(frame)),
            "best_candidate": best_dict,
            "key_metrics": key_metrics,
            "columns": list(frame.columns),
        },
    )


def inspect_score_summary(score_summary_path: str | Path) -> ToolResult:
    path = Path(score_summary_path)
    if not path.exists():
        return ToolResult("inspect_score_summary", "fail", {"path": str(path)}, failures=[f"missing score_summary: {path}"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    warnings = []
    for field in ["data_source", "engineering_validity"]:
        if field not in payload:
            warnings.append(f"missing boundary field: {field}")
    data = {
        "path": str(path),
        "schema_version": payload.get("schema_version"),
        "result_version": payload.get("result_version"),
        "hard_constraint_passed": payload.get("hard_constraint_passed"),
        "hard_constraint_failures": payload.get("hard_constraint_failures", []),
        "failure_reasons": payload.get("failure_reasons", []),
        "warning_reasons": payload.get("warning_reasons", []),
        "soft_scores": payload.get("soft_scores", {}),
        "overall_score": payload.get("overall_score"),
        "data_source": payload.get("data_source"),
        "engineering_validity": payload.get("engineering_validity"),
    }
    return ToolResult("inspect_score_summary", "warning" if warnings else "pass", data, warnings=warnings)


def inspect_real_metrics(real_metrics_path: str | Path) -> ToolResult:
    path = Path(real_metrics_path)
    if not path.exists():
        return ToolResult("inspect_real_metrics", "fail", {"path": str(path)}, failures=[f"missing real_metrics: {path}"])
    frame = pd.read_csv(path)
    bad_mask = frame.isna()
    for column in frame.columns:
        bad_mask[column] = bad_mask[column] | frame[column].astype(str).str.lower().isin(BAD_CELL_STRINGS)
    bad_cells = int(bad_mask.sum().sum())
    bad_cell_values = sorted(
        {
            str(value).strip().lower()
            for column in frame.columns
            for value in frame.loc[bad_mask[column], column].tolist()
            if str(value).strip()
        }
    )
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    worst_stage = None
    if "stage" in frame.columns:
        risk_columns = [column for column in ["Ripple", "OverlapRatio", "VoltageLoss", "FalseTriggerCount", "Delay"] if column in numeric.columns]
        if risk_columns:
            risk = numeric[risk_columns].fillna(0).sum(axis=1)
            worst_stage = _jsonable(frame.iloc[int(risk.idxmax())].to_dict())
    stats: dict[str, Any] = {}
    for column in ["Ripple", "OverlapRatio", "VoltageLoss", "FalseTriggerCount", "Delay", "RiseTime", "FallTime"]:
        if column in numeric:
            series = numeric[column].dropna()
            if not series.empty:
                stats[column] = {"min": float(series.min()), "max": float(series.max()), "mean": float(series.mean())}
    data = {
        "path": str(path),
        "row_count": int(len(frame)),
        "bad_cell_count": bad_cells,
        "worst_stage": worst_stage,
        "metric_stats": stats,
        "bad_cell_values": bad_cell_values,
        "columns": list(frame.columns),
    }
    return ToolResult("inspect_real_metrics", "warning" if bad_cells else "pass", data, warnings=["bad metric cells detected"] if bad_cells else [])


def generate_candidates(
    leaderboard_path: str | Path,
    param_space_path: str | Path,
    output_dir: str | Path,
    max_candidates: int = 10,
) -> ToolResult:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    param_space = _load_param_values(Path(param_space_path))
    recommendations = _recommendations_from_leaderboard(Path(leaderboard_path))
    candidates = rank_candidates(propose_candidates(param_space, recommendations))[: int(max_candidates or 10)]
    rows = []
    for index, candidate in enumerate(candidates, start=1):
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "result_version": RESULT_VERSION,
                "candidate_id": f"next_{index:03d}",
                "parameter": candidate.get("parameter"),
                "direction": candidate.get("direction"),
                "candidate_values": json.dumps(candidate.get("candidate_values", []), ensure_ascii=False),
                "priority": candidate.get("priority"),
                "source_recommendation": candidate.get("source_recommendation"),
                "trigger_metric": candidate.get("trigger_metric"),
                "parameter_change_count": 1,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        )
    path = output / "next_candidates.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    status = "pass" if rows else "warning"
    warnings = [] if rows else ["optimizer wrapper produced no candidates from available recommendations"]
    return ToolResult(
        "generate_candidates",
        status,
        {
            "next_candidates_path": str(path),
            "candidate_count": len(rows),
            "recommendation_count": len(recommendations),
            "candidate_summary": rows[:3],
        },
        warnings=warnings,
    )


def inspect_candidates(next_candidates_path: str | Path, param_space_path: str | Path, max_parameter_changes: int = 2) -> ToolResult:
    path = Path(next_candidates_path)
    if not path.exists():
        return ToolResult("inspect_candidates", "fail", {"path": str(path)}, failures=[f"missing candidates: {path}"])
    frame = pd.read_csv(path)
    param_space = _load_param_values(Path(param_space_path)) if param_space_path else {}
    issues: list[str] = []
    for _, row in frame.iterrows():
        parameter = row.get("parameter")
        allowed = set(str(value) for value in param_space.get(str(parameter), []))
        values = _parse_candidate_values(row.get("candidate_values"))
        for value in values:
            if allowed and str(value) not in allowed:
                issues.append(f"candidate {row.get('candidate_id')} parameter {parameter} value {value} outside param_space")
        change_count = int(row.get("parameter_change_count", 1) or 1)
        if change_count > max_parameter_changes:
            issues.append(f"candidate {row.get('candidate_id')} parameter change count {change_count} exceeds {max_parameter_changes}")
    data = {
        "path": str(path),
        "candidate_count": int(len(frame)),
        "issues": issues,
        "max_parameter_changes": max_parameter_changes,
    }
    return ToolResult("inspect_candidates", "warning" if issues else "pass", data, warnings=issues)


def inspect_netlist_integrity(netlist_path: str | Path) -> ToolResult:
    path = Path(netlist_path)
    if not path.exists():
        return ToolResult("inspect_netlist_integrity", "fail", {"path": str(path)}, failures=[f"missing netlist: {path}"])

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    issues: list[str] = []
    subckt_stack: list[tuple[str, int]] = []
    has_end = False

    for line_no, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        upper = stripped.upper()
        tokens = stripped.split()
        directive = tokens[0].upper() if tokens else ""
        if directive == ".END":
            has_end = True
        elif directive == ".SUBCKT":
            name = tokens[1] if len(tokens) > 1 else "<missing-name>"
            subckt_stack.append((name, line_no))
        elif directive == ".ENDS":
            end_name = tokens[1] if len(tokens) > 1 else None
            if not subckt_stack:
                issues.append(f"netlist has .ENDS without matching .SUBCKT at line {line_no}")
            else:
                start_name, start_line = subckt_stack.pop()
                if end_name and end_name != start_name:
                    issues.append(f"netlist .ENDS {end_name} at line {line_no} does not match .SUBCKT {start_name} at line {start_line}")
        elif upper.startswith(".END") and directive not in {".END", ".ENDS"}:
            issues.append(f"netlist has ambiguous end directive at line {line_no}: {tokens[0]}")

    if not has_end:
        issues.append("netlist missing .END directive")
    for name, line_no in subckt_stack:
        issues.append(f"netlist has .SUBCKT without matching .ENDS: {name} at line {line_no}")

    parsed = parse_netlist(path)
    kind_counts: dict[str, int] = {}
    for device in parsed.devices:
        kind_counts[device.kind] = kind_counts.get(device.kind, 0) + 1
    has_mos_evidence = any(device.kind == "mos" for device in parsed.devices) or any(_looks_like_mos_line(line) for line in lines)
    if not has_mos_evidence:
        issues.append("netlist missing MOS devices")
    if not any(device.kind == "voltage_source" for device in parsed.devices):
        issues.append("netlist missing voltage sources")
    issues.extend(parsed.warnings)

    data = {
        "path": str(path),
        "line_count": len(lines),
        "device_count": len(parsed.devices),
        "subckt_count": len(parsed.subckts),
        "kind_counts": kind_counts,
        "has_mos_evidence": has_mos_evidence,
        "issues": issues,
    }
    return ToolResult("inspect_netlist_integrity", "warning" if issues else "pass", data, warnings=issues)


def check_schema_and_boundary(
    output_path: str | Path,
    expected_data_source: str = "real_simulation_csv",
    expected_engineering_validity: str = "simulation_only",
) -> ToolResult:
    path = Path(output_path)
    if not path.exists():
        return ToolResult("check_schema_and_boundary", "fail", {"path": str(path)}, failures=[f"missing output file: {path}"])
    issues: list[str] = []
    payload: dict[str, Any] = {}
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, nrows=1)
        payload = frame.iloc[0].to_dict() if not frame.empty else {}
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        payload = {"text": text}
    if "schema_version" not in payload and "result_version" not in payload:
        issues.append("schema_version/result_version missing")
    if payload.get("data_source") != expected_data_source:
        issues.append(f"data_source mismatch or missing: {payload.get('data_source')}")
    if payload.get("engineering_validity") != expected_engineering_validity:
        issues.append(f"engineering_validity mismatch or missing: {payload.get('engineering_validity')}")
    return ToolResult(
        "check_schema_and_boundary",
        "warning" if issues else "pass",
        {"path": str(path), "issues": issues, "payload_keys": list(payload.keys())},
        warnings=issues,
    )


def write_multi_agent_report(final_state: dict, memory: dict, trace: list, handoff_trace: list, critic_report: dict, output_dir: str | Path) -> ToolResult:
    from goa_eval.multi_agent.optimization_loop import write_optimization_artifacts
    from goa_eval.multi_agent.report_writer import write_decision_report

    artifact_paths = write_optimization_artifacts(Path(output_dir), final_state, critic_report)
    final_state.setdefault("generated_files", {}).update(artifact_paths)
    path = write_decision_report(Path(output_dir), final_state, memory, trace, handoff_trace, critic_report)
    return ToolResult("write_multi_agent_report", "pass", {"report_path": str(path), **artifact_paths})


def _input_kind(key: str) -> str:
    if key in {"leaderboard", "score_summary", "real_metrics", "waveform", "netlist", "param_space"}:
        return key
    return "unknown"


def _looks_like_mos_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("*") or stripped.startswith("."):
        return False
    tokens = stripped.split()
    if not tokens:
        return False
    name = tokens[0].lower()
    if name.startswith("m"):
        return True
    if name.startswith("xm") and any("fet" in token.lower() for token in tokens[1:]):
        return True
    return False


def _load_param_values(path: Path) -> dict[str, list[Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", raw)
    normalized: dict[str, list[Any]] = {}
    for key, value in parameters.items():
        if isinstance(value, dict) and "values" in value:
            normalized[key] = list(value["values"])
        elif isinstance(value, list):
            normalized[key] = value
        else:
            normalized[key] = [value]
    return normalized


def _recommendations_from_leaderboard(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
    text = " ".join(str(value).lower() for value in frame.astype(str).to_numpy().ravel()) if not frame.empty else ""
    recommendations = []
    triggers = [
        ("Max_ripple", "ripple_hold_window_review", "ripple"),
        ("Delay_mean", "delay_drive_load_review", "delay"),
        ("Max_overlap_ratio", "overlap_timing_review", "overlap"),
        ("FalseTriggerCount", "false_trigger_threshold_review", "false_trigger"),
    ]
    for metric, rec_id, token in triggers:
        if token in text or metric in frame.columns:
            recommendations.append({"recommendation_id": rec_id, "trigger_metric": metric})
    if not recommendations:
        recommendations.append({"recommendation_id": "delay_drive_load_review", "trigger_metric": "Delay_mean"})
    return recommendations


def _parse_candidate_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    text = str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            parsed = [text]
    return parsed if isinstance(parsed, list) else [parsed]


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
