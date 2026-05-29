from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import inspect_analysis_metrics, inspect_existing_reports, inspect_leaderboard, inspect_real_metrics, inspect_real_summary, inspect_score_summary


def run_goa_agent(state: dict) -> dict:
    state["active_agent"] = "GOAAgent"
    inputs = state.get("inputs", {})
    if inputs.get("leaderboard"):
        result = inspect_leaderboard(inputs["leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("score_summary"):
        result = inspect_score_summary(inputs["score_summary"])
        state["score_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("real_metrics"):
        result = inspect_real_metrics(inputs["real_metrics"])
        state["metrics_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("real_summary"):
        result = inspect_real_summary(inputs["real_summary"])
        state["real_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    if inputs.get("analysis_metrics"):
        result = inspect_analysis_metrics(inputs["analysis_metrics"])
        state["analysis_metrics_summary"] = result.data
        store_tool_result(state, "GOAAgent", result)
    result = inspect_existing_reports(inputs)
    state["existing_report_summary"] = result.data
    store_tool_result(state, "GOAAgent", result)
    diagnosis = {
        "domain": "GOA/8T1C",
        "real_summary": state.get("real_summary", {}),
        "reports": state.get("existing_report_summary", {}),
        "cascade_stage_risk": {
            "worst_stage": state.get("metrics_summary", {}).get("worst_stage"),
            "first_failed_stage": state.get("score_summary", {}).get("first_failed_stage"),
        },
        "overlap": state.get("metrics_summary", {}).get("metric_stats", {}).get("OverlapRatio"),
        "ripple": state.get("metrics_summary", {}).get("metric_stats", {}).get("Ripple"),
        "voltage_loss": state.get("metrics_summary", {}).get("metric_stats", {}).get("VoltageLoss"),
        "false_trigger": state.get("metrics_summary", {}).get("metric_stats", {}).get("FalseTriggerCount"),
        "analysis_metrics": state.get("analysis_metrics_summary", {}),
        "goa_benchmark": state.get("analysis_metrics_summary", {}).get("goa_benchmark_metrics", {}),
        "next_direction": "prioritize overlap window, ripple hold-window, voltage-loss, and false-trigger review before wider parameter search",
    }
    state["domain_diagnosis"] = diagnosis
    add_message(
        state,
        "GOAAgent",
        {
            "goa_summary": "GOA/8T1C evaluation artifacts inspected.",
            "domain_diagnosis": diagnosis,
            "goa_next_action": "run shared evaluation and candidate generation only through deterministic tools",
        },
    )
    append_handoff(
        state,
        "GOAAgent",
        "EvaluationAgent",
        "domain artifacts inspected",
        ["real_summary", "leaderboard_summary", "score_summary", "metrics_summary", "analysis_metrics_summary", "existing_report_summary"],
    )
    return state
