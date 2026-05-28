from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import (
    inspect_analysis_metrics,
    inspect_existing_reports,
    inspect_leaderboard,
    inspect_optimization_history,
    inspect_real_metrics,
    inspect_run_manifest,
    inspect_score_summary,
    inspect_validation_summary,
)


def run_sky130_agent(state: dict) -> dict:
    state["active_agent"] = "SKY130Agent"
    inputs = state.get("inputs", {})
    if inputs.get("leaderboard"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("real_metrics"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("analysis_metrics"):
        result = inspect_analysis_metrics(inputs["analysis_metrics"])
        state["analysis_metrics_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("validation_summary"):
        result = inspect_validation_summary(inputs["validation_summary"])
        state["validation_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("optimization_history"):
        result = inspect_optimization_history(inputs["optimization_history"])
        state["optimization_history_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    if inputs.get("run_manifest_real"):
        result = inspect_run_manifest(inputs["run_manifest_real"])
        state["run_manifest_summary"] = result.data
        store_tool_result(state, "SKY130Agent", result)
    result = inspect_existing_reports(inputs)
    state["existing_report_summary"] = result.data
    store_tool_result(state, "SKY130Agent", result)
    best_candidate = state.get("leaderboard_summary", {}).get("best_candidate", {})
    diagnosis = {
        "domain": "SKY130",
        "analysis_metrics": state.get("analysis_metrics_summary", {}),
        "validation": {
            "failed_targets": state.get("validation_summary", {}).get("failed_targets", []),
            "status_counts": state.get("validation_summary", {}).get("status_counts", {}),
        },
        "optimization_history": state.get("optimization_history_summary", {}),
        "run_manifest": state.get("run_manifest_summary", {}),
        "sky130_timing": {
            key: state.get("metrics_summary", {}).get("metric_stats", {}).get(key)
            for key in ["Delay", "RiseTime", "FallTime"]
        },
        "parameter_focus": {
            "load_cap": best_candidate.get("load_cap"),
            "drive_resistance": best_candidate.get("drive_resistance"),
            "candidate_risk_summary": state.get("candidate_summary", {}),
        },
        "hard_constraints": {
            "passed": state.get("score_summary", {}).get("hard_constraint_passed"),
            "failures": state.get("score_summary", {}).get("hard_constraint_failures", []),
        },
        "timing_margin": "review delay/rise/fall against hard constraints before accepting any candidate",
        "next_direction": "generate bounded param_space candidates and rerun through simulation-only evaluation",
    }
    state["domain_diagnosis"] = diagnosis
    add_message(
        state,
        "SKY130Agent",
        {
            "sky130_summary": "SKY130 leaderboard and scoring artifacts inspected.",
            "best_candidate_summary": best_candidate,
            "domain_diagnosis": diagnosis,
            "score_summary": state.get("score_summary", {}),
            "candidate_risk_summary": state.get("candidate_summary", {}),
            "sky130_next_action": "generate next candidates through optimizer wrapper if param_space is available",
        },
    )
    append_handoff(
        state,
        "SKY130Agent",
        "EvaluationAgent",
        "domain artifacts inspected",
        [
            "leaderboard_summary",
            "score_summary",
            "metrics_summary",
            "analysis_metrics_summary",
            "validation_summary",
            "optimization_history_summary",
            "run_manifest_summary",
        ],
    )
    return state
