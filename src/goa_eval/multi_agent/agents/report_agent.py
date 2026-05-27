from __future__ import annotations

from goa_eval.multi_agent.agents._utils import store_tool_result
from goa_eval.multi_agent.memory import build_memory
from goa_eval.multi_agent.tools import write_multi_agent_report


def run_report_agent(state: dict) -> dict:
    state["active_agent"] = "ReportAgent"
    critic_report = {"verdicts": state.get("critic_verdicts", [])}
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
    store_tool_result(state, "ReportAgent", result)
    return state
