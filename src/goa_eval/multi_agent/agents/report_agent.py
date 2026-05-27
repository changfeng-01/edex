from __future__ import annotations

from goa_eval.multi_agent.agents._utils import store_tool_result
from goa_eval.multi_agent.memory import build_memory
from goa_eval.multi_agent.tools import write_multi_agent_report


def run_report_agent(state: dict) -> dict:
    state["active_agent"] = "ReportAgent"
    critic_report = _critic_report_from_state(state)
    memory = build_memory(state).to_dict()
    result = write_multi_agent_report(
        state,
        memory,
        state.get("trace_records", []),
        state.get("handoff_records", []),
        critic_report,
        state["output_dir"],
    )
    if result.data.get("report_path"):
        state.setdefault("generated_files", {})["multi_agent_decision_report"] = result.data["report_path"]
    if result.data.get("optimization_loop_record"):
        state.setdefault("generated_files", {})["optimization_loop_record"] = result.data["optimization_loop_record"]
    if result.data.get("optimization_decision_card"):
        state.setdefault("generated_files", {})["optimization_decision_card"] = result.data["optimization_decision_card"]
    store_tool_result(state, "ReportAgent", result)
    return state


def _critic_report_from_state(state: dict) -> dict:
    risks = [risk for verdict in state.get("critic_verdicts", []) for risk in verdict.get("risks", [])]
    return {
        "verdicts": state.get("critic_verdicts", []),
        "warnings": state.get("warnings", []),
        "failures": state.get("failures", []),
        "risk_summary": _risk_summary(risks),
        "top_risks": risks[:5],
    }


def _risk_summary(risks: list[dict]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for risk in risks:
        risk_type = str(risk.get("risk_type", "unknown"))
        severity = str(risk.get("severity", "info"))
        summary.setdefault(risk_type, {})
        summary[risk_type][severity] = summary[risk_type].get(severity, 0) + 1
    return summary
