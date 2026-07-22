from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from goa_eval.io_utils import read_json as _read_json
from goa_eval.multi_agent.agent_contracts import is_tool_allowed
from goa_eval.multi_agent.schemas import CriticVerdict
from goa_eval.multi_agent.tools import BAD_CELL_STRINGS, check_schema_and_boundary, inspect_candidates, inspect_netlist_integrity, normalize_artifact_inputs


DEFAULT_MAX_OVERLAP_RATIO = 0.1


def run_critic_checks(state: dict) -> list[CriticVerdict]:
    verdicts: list[CriticVerdict] = []
    issues: list[str] = []
    failures: list[str] = []

    for label, path_text in (state.get("generated_files") or {}).items():
        path = Path(str(path_text))
        if not path.exists():
            issues.append(f"missing output file: {label} -> {path}")
            continue
        if path.suffix.lower() in {".json", ".csv"}:
            boundary = check_schema_and_boundary(path, state.get("data_source", "real_simulation_csv"), state.get("engineering_validity", "simulation_only"))
            issues.extend(boundary.warnings)
        if path.suffix.lower() == ".csv":
            issues.extend(_bad_metric_cell_issues(path))

    allowed_data_sources = {"real_simulation_csv"}
    if state.get("selected_domain_agent") == "InstrumentationAmplifierAgent":
        allowed_data_sources.add("analytic_model_proxy")
    if state.get("data_source") not in allowed_data_sources:
        issues.append(f"data_source mismatch: {state.get('data_source')}")
    if state.get("engineering_validity") != "simulation_only":
        issues.append(f"engineering_validity mismatch: {state.get('engineering_validity')}")
    inputs = normalize_artifact_inputs(state.get("inputs") or {})
    _extend_missing_evidence_issues(state, issues)
    _extend_main_artifact_issues(inputs, issues, failures)
    bad_metric_count = int((state.get("metrics_summary") or {}).get("bad_cell_count") or 0)
    if bad_metric_count:
        issues.append(f"bad metric cell count {bad_metric_count} in inspected metrics")
    _extend_domain_risk_issues(state, issues, failures)
    if state.get("selected_domain_agent") == "unsupported" or state.get("profile") == "unknown":
        issues.append("unsupported profile routed to critic")
    if not state.get("handoff_records"):
        issues.append("handoff record missing")
    _extend_optimization_loop_issues(state, issues)

    candidate_path = (state.get("generated_files") or {}).get("next_candidates") or inputs.get("next_candidates")
    param_space = inputs.get("param_space")
    if candidate_path and Path(str(candidate_path)).exists() and param_space:
        result = inspect_candidates(candidate_path, param_space, int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)))
        issues.extend(result.warnings)

    netlist_path = inputs.get("netlist")
    if netlist_path:
        result = inspect_netlist_integrity(netlist_path)
        issues.extend(result.warnings)
        failures.extend(result.failures)

    for agent_name, results in (state.get("tool_results") or {}).items():
        for result in results:
            tool_name = result.get("tool_name")
            if tool_name and not is_tool_allowed(agent_name, tool_name):
                issues.append(f"unauthorized tool call: {agent_name} -> {tool_name}")

    report_path = (state.get("generated_files") or {}).get("multi_agent_decision_report")
    if report_path and Path(str(report_path)).exists():
        text = Path(str(report_path)).read_text(encoding="utf-8", errors="replace").lower()
        issues.extend(_forbidden_claim_issues(text, "multi_agent_decision_report"))

    all_issues = [*failures, *issues]
    risks = _classify_issues(all_issues)
    severity = _max_severity(risks)
    primary_risk_type = risks[0]["risk_type"] if risks else "none"
    verdict = "pass" if not all_issues else "reject" if severity in {"critical", "major"} and failures else "warning"
    verdicts.append(
        CriticVerdict(
            step_id=f"critic-{len(state.get('critic_verdicts', [])) + 1}",
            agent_name="CriticAgent",
            verdict=verdict,
            issues=all_issues,
            reason="critic checks completed",
            suggested_next_action="continue with simulation-only reporting" if verdict == "pass" else "review warnings before using outputs",
            severity=severity,
            risk_type=primary_risk_type,
            risks=risks,
        )
    )
    return verdicts


def _bad_metric_cell_issues(path: Path) -> list[str]:
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return [f"csv unreadable: {path}: {exc}"]
    issues = []
    bad_mask = frame.isna()
    for column in frame.columns:
        bad_mask[column] = bad_mask[column] | frame[column].astype(str).str.lower().isin(BAD_CELL_STRINGS)
    count = int(bad_mask.sum().sum())
    if count:
        issues.append(f"bad metric cell count {count} in {path}")
    return issues


def _extend_missing_evidence_issues(state: dict, issues: list[str]) -> None:
    evidence = state.get("evidence_index") or {}
    artifacts = evidence.get("artifacts") or {}
    if not evidence:
        issues.append("missing evidence_index in shared state")
        return
    if state.get("selected_domain_agent") in {"GOAAgent", "GenericWaveformAgent"}:
        for key in ["real_summary", "real_metrics", "score_summary"]:
            if not (artifacts.get(key) or {}).get("exists"):
                issues.append(f"missing evidence artifact: {key}")


def _extend_main_artifact_issues(inputs: dict, issues: list[str], failures: list[str]) -> None:
    real_summary = _read_json(inputs.get("real_summary"))
    if real_summary:
        _check_boundary_payload(real_summary, "real_summary", issues)
        if _contains_bad_cell(real_summary):
            issues.append("not_evaluable or missing metric value detected in real_summary")
        false_trigger = _numeric(real_summary.get("FalseTriggerCount") or real_summary.get("False_trigger_count"))
        if false_trigger is not None and false_trigger > 0:
            issues.append(f"FalseTriggerCount above zero in real_summary: {false_trigger}")
        overlap = _numeric(real_summary.get("Max_overlap_ratio"))
        if overlap is not None and overlap > DEFAULT_MAX_OVERLAP_RATIO:
            issues.append(f"Max_overlap_ratio above limit in real_summary: {overlap} > {DEFAULT_MAX_OVERLAP_RATIO}")
        ripple = _numeric(real_summary.get("Max_ripple"))
        ripple_limit = _numeric(real_summary.get("max_ripple_v_limit"))
        if ripple is not None and ripple_limit is not None and ripple > ripple_limit:
            issues.append(f"Max_ripple above limit in real_summary: {ripple} > {ripple_limit}")

    score_summary = _read_json(inputs.get("score_summary"))
    if score_summary:
        _check_boundary_payload(score_summary, "score_summary", issues)
        if score_summary.get("hard_constraint_passed") is False:
            failures.append("hard_constraint_failed: score_summary hard_constraint_passed is false")
        if score_summary.get("not_evaluable_metrics"):
            issues.append(f"profile metric missingness: {score_summary.get('not_evaluable_metrics')}")
        penalties = score_summary.get("analysis_metric_penalties") or {}
        missing_penalties = [key for key, value in penalties.items() if _contains_bad_cell(value)]
        if missing_penalties:
            issues.append(f"profile metric missingness in analysis_metric_penalties: {missing_penalties}")

    analysis_metrics = _read_json(inputs.get("analysis_metrics"))
    if analysis_metrics and _contains_bad_cell(analysis_metrics):
        issues.append("profile metric missingness in analysis_metrics")

    validation_path = inputs.get("validation_summary")
    if validation_path and Path(str(validation_path)).exists():
        try:
            frame = pd.read_csv(validation_path)
            if "target.status" in frame.columns:
                bad_targets = frame[frame["target.status"].astype(str).str.lower() != "passed"]
                if not bad_targets.empty:
                    issues.append(f"validation target status not passed: {bad_targets['target.status'].astype(str).tolist()}")
            elif "status" in frame.columns:
                bad_status = frame[frame["status"].astype(str).str.lower().isin({"failed", "fail", "error"})]
                if not bad_status.empty:
                    issues.append(f"validation target status failed: {bad_status['status'].astype(str).tolist()}")
        except Exception as exc:
            issues.append(f"validation_summary unreadable: {validation_path}: {exc}")

    if inputs.get("next_candidates") and not any(inputs.get(key) for key in ["optimization_history", "optimization_leaderboard", "rerun_leaderboard"]):
        issues.append("optimization rerun missingness: candidate artifacts exist without optimization history or rerun leaderboard")

    run_manifest = _read_json(inputs.get("run_manifest_real"))
    if run_manifest:
        _check_boundary_payload(run_manifest, "run_manifest_real", issues)

    for key in ["diagnosis_report", "real_waveform_report"]:
        path_text = inputs.get(key)
        if path_text and Path(str(path_text)).exists():
            text = Path(str(path_text)).read_text(encoding="utf-8", errors="replace").lower()
            issues.extend(_forbidden_claim_issues(text, key))


def _check_boundary_payload(payload: dict, label: str, issues: list[str]) -> None:
    if payload.get("data_source") != "real_simulation_csv":
        issues.append(f"data_source mismatch in {label}: {payload.get('data_source')}")
    if payload.get("engineering_validity") != "simulation_only":
        issues.append(f"engineering_validity mismatch in {label}: {payload.get('engineering_validity')}")


def _forbidden_claim_issues(text: str, label: str) -> list[str]:
    issues = []
    forbidden = ["silicon validation", "physical validation", "tape-out proof", "real chip verification", "industrial-grade full automation"]
    for phrase in forbidden:
        index = text.find(phrase)
        if index >= 0 and "not" not in text[max(0, index - 20) : index]:
            issues.append(f"{label} may overclaim forbidden phrase: {phrase}")
    return issues


def _extend_domain_risk_issues(state: dict, issues: list[str], failures: list[str]) -> None:
    score_summary = state.get("score_summary") or {}
    metrics_summary = state.get("metrics_summary") or {}
    if score_summary.get("hard_constraint_passed") is False:
        failure_text = ", ".join(str(item) for item in score_summary.get("hard_constraint_failures", []) or score_summary.get("failure_reasons", []))
        failures.append(f"hard_constraint_failed: {failure_text or 'score_summary hard_constraint_passed is false'}")
    for field in ["data_source", "engineering_validity"]:
        if score_summary and field not in score_summary:
            issues.append(f"missing boundary field in score_summary: {field}")
    bad_values = metrics_summary.get("bad_cell_values") or []
    if _contains_bad_cell(score_summary) or _contains_bad_cell(metrics_summary):
        suffix = f": {', '.join(str(value) for value in bad_values)}" if bad_values else ""
        issues.append(f"not_evaluable or missing metric value detected in agent state{suffix}")

    metric_stats = metrics_summary.get("metric_stats") or {}
    false_trigger = metric_stats.get("FalseTriggerCount") or {}
    if _numeric(false_trigger.get("max")) and float(false_trigger.get("max")) > 0:
        issues.append(f"FalseTriggerCount above zero: {false_trigger.get('max')}")
    worst_stage = metrics_summary.get("worst_stage") or {}
    if str(worst_stage.get("FalseTrigger")).lower() == "true":
        issues.append(f"FalseTrigger detected at worst_stage: {worst_stage.get('node') or worst_stage.get('stage')}")

    overlap = metric_stats.get("OverlapRatio") or {}
    overlap_limit = _overlap_limit(state)
    overlap_max = _numeric(overlap.get("max"))
    if overlap_max is not None and overlap_max > overlap_limit:
        issues.append(f"OverlapRatio above limit: {overlap_max} > {overlap_limit}")


def _extend_optimization_loop_issues(state: dict, issues: list[str]) -> None:
    candidate_count = int((state.get("candidate_summary") or {}).get("candidate_count") or 0)
    inputs = state.get("inputs") or {}
    has_rerun = any(inputs.get(key) for key in ["rerun_run_dir", "rerun_leaderboard", "rerun_score_summary", "rerun_real_metrics"])
    if candidate_count and not has_rerun:
        issues.append("rerun results missing: optimization loop is awaiting_rerun_results")


def _classify_issues(issues: list[str]) -> list[dict[str, str]]:
    return [_classify_issue(issue) for issue in issues]


def _classify_issue(issue: str) -> dict[str, str]:
    text = issue.lower()
    if "hard_constraint" in text:
        return _risk(issue, "hard_constraint", "critical")
    if "falsetrigger" in text or "false trigger" in text:
        return _risk(issue, "false_trigger", "critical")
    if "overlapratio" in text or "overlap ratio" in text or "max_overlap_ratio" in text:
        return _risk(issue, "overlap", "major")
    if "not_evaluable" in text or "bad metric" in text:
        return _risk(issue, "not_evaluable", "major")
    if "profile metric missingness" in text:
        return _risk(issue, "profile_metric_missingness", "warning")
    if "optimization rerun missingness" in text:
        return _risk(issue, "optimization_rerun_missingness", "warning")
    if "validation target status" in text:
        return _risk(issue, "validation_target_status", "major")
    if "forbidden phrase" in text or "overclaim" in text:
        return _risk(issue, "physical_validation_claim", "critical")
    if "unauthorized tool" in text:
        return _risk(issue, "tool_permission", "major")
    if "netlist" in text:
        return _risk(issue, "netlist_integrity", "warning")
    if "candidate" in text or "parameter" in text or "param_space" in text:
        return _risk(issue, "candidate_risk", "warning")
    if "rerun results missing" in text:
        return _risk(issue, "rerun_missing", "warning")
    if "decision" in text:
        return _risk(issue, "decision_blocked", "warning")
    if "boundary" in text or "data_source" in text or "engineering_validity" in text or "schema_version" in text:
        return _risk(issue, "boundary", "major")
    return _risk(issue, "boundary", "warning")


def _risk(issue: str, risk_type: str, severity: str) -> dict[str, str]:
    return {"risk_type": risk_type, "severity": severity, "issue": issue}


def _max_severity(risks: list[dict[str, str]]) -> str:
    order = {"info": 0, "warning": 1, "major": 2, "critical": 3}
    if not risks:
        return "info"
    return max((risk.get("severity", "info") for risk in risks), key=lambda item: order.get(item, 0))


def _contains_bad_cell(value) -> bool:
    if isinstance(value, dict):
        return any(_contains_bad_cell(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_bad_cell(item) for item in value)
    text = str(value).strip().lower()
    return text in BAD_CELL_STRINGS


def _overlap_limit(state: dict) -> float:
    limits = state.get("limits") or {}
    for key in ["max_overlap_ratio", "Max_overlap_ratio", "overlap_ratio_limit"]:
        value = _numeric(limits.get(key))
        if value is not None:
            return value
    return DEFAULT_MAX_OVERLAP_RATIO


def _numeric(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
