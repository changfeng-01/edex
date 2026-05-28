from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goa_eval.multi_agent.schemas import AgentStep


def record_step(
    state: dict,
    *,
    agent_name: str,
    node_name: str,
    step_id: str,
    status: str,
    reason: str = "",
    tool_name: str | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    critic_verdict: str | None = None,
) -> dict:
    step = AgentStep(
        agent_name=agent_name,
        node_name=node_name,
        step_id=step_id,
        status=status,
        reason=reason,
        tool_name=tool_name,
        input_summary=input_summary or {},
        output_summary=output_summary or {},
        critic_verdict=critic_verdict,
    )
    state.setdefault("trace_records", []).append(step.to_dict())
    return state


def write_trace(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
