from __future__ import annotations

from typing import Any

from goa_eval.multi_agent.agent_contracts import is_tool_allowed
from goa_eval.multi_agent.schemas import ToolResult
from goa_eval.multi_agent.trace import record_step


def store_tool_result(state: dict, agent_name: str, result: ToolResult) -> dict:
    payload = result.to_dict()
    state.setdefault("tool_results", {}).setdefault(agent_name, []).append(payload)
    state.setdefault("warnings", []).extend(result.warnings)
    state.setdefault("failures", []).extend(result.failures)
    if not is_tool_allowed(agent_name, result.tool_name):
        state.setdefault("warnings", []).append(f"unauthorized tool call attempted: {agent_name} -> {result.tool_name}")
    record_step(
        state,
        agent_name=agent_name,
        node_name=agent_name,
        step_id=f"{agent_name}-{len(state.get('trace_records', [])) + 1}",
        tool_name=result.tool_name,
        status=result.status,
        input_summary={},
        output_summary=result.data,
        reason="tool executed",
    )
    return state


def add_message(state: dict, agent_name: str, message: dict[str, Any]) -> None:
    state.setdefault("agent_messages", []).append({"agent_name": agent_name, **message})
    record_step(
        state,
        agent_name=agent_name,
        node_name=agent_name,
        step_id=f"{agent_name}-{len(state.get('trace_records', [])) + 1}",
        status="pass",
        reason="agent message recorded",
        output_summary=message,
    )
