from __future__ import annotations

from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.router import route_task
from goa_eval.multi_agent.tools import inspect_task_inputs


def run_router_agent(state: dict) -> dict:
    state["active_agent"] = "RouterAgent"
    result = inspect_task_inputs(state.get("inputs", {}))
    store_tool_result(state, "RouterAgent", result)
    decision = route_task(state.get("task_type", ""), state.get("profile", ""), state.get("inputs", {}))
    state["selected_domain_agent"] = decision["selected_domain_agent"]
    state["next_agent"] = decision["handoff_to"]
    state["routing_reason"] = decision["reason"]
    append_handoff(
        state,
        "RouterAgent",
        decision["handoff_to"],
        decision["reason"],
        ["task_name", "task_type", "profile", "inputs", "objectives"],
    )
    add_message(state, "RouterAgent", decision)
    return state
