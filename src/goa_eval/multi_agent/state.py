from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from goa_eval.multi_agent.schemas import JsonDataclass, MultiAgentTask


@dataclass
class MultiAgentEDAState(JsonDataclass):
    task_name: str = ""
    task_type: str = ""
    profile: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    objectives: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    validity: dict[str, Any] = field(default_factory=dict)
    active_agent: str | None = None
    selected_domain_agent: str | None = None
    next_agent: str | None = None
    agent_messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    handoff_records: list[dict[str, Any]] = field(default_factory=list)
    leaderboard_summary: dict[str, Any] = field(default_factory=dict)
    score_summary: dict[str, Any] = field(default_factory=dict)
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    candidate_summary: dict[str, Any] = field(default_factory=dict)
    critic_verdicts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    generated_files: dict[str, str] = field(default_factory=dict)
    output_dir: str = ""
    data_source: str = "real_simulation_csv"
    engineering_validity: str = "simulation_only"
    trace_records: list[dict[str, Any]] = field(default_factory=list)
    task: dict[str, Any] = field(default_factory=dict)


def new_state_from_task(task: MultiAgentTask, output_dir: str) -> dict[str, Any]:
    data_source = str(task.validity.get("data_source", "real_simulation_csv"))
    engineering_validity = str(task.validity.get("engineering_validity", "simulation_only"))
    return MultiAgentEDAState(
        task_name=task.task_name,
        task_type=task.task_type,
        profile=task.profile,
        inputs=task.inputs,
        objectives=task.objectives,
        limits=task.limits,
        validity=task.validity,
        output_dir=str(output_dir),
        data_source=data_source,
        engineering_validity=engineering_validity,
        task=task.to_dict(),
    ).to_dict()
