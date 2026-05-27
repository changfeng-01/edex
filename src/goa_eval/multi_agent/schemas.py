from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


@dataclass
class JsonDataclass:
    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass
class MultiAgentTask(JsonDataclass):
    task_name: str
    task_type: str
    profile: str
    inputs: dict[str, Any] = field(default_factory=dict)
    objectives: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    validity: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContract(JsonDataclass):
    agent_name: str
    role: str
    description: str
    allowed_tools: list[str]
    input_schema: list[str]
    output_schema: list[str]
    handoff_policy: dict[str, Any]
    failure_policy: dict[str, Any]
    memory_scope: str = "run_local"


@dataclass
class AgentStep(JsonDataclass):
    agent_name: str
    node_name: str
    step_id: str
    status: str
    reason: str = ""
    tool_name: str | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    critic_verdict: str | None = None
    timestamp: str = field(default_factory=utc_timestamp)


@dataclass
class ToolResult(JsonDataclass):
    tool_name: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_timestamp)


@dataclass
class ToolMetadata(JsonDataclass):
    tool_name: str
    description: str
    input_requirements: list[str]
    output_description: str
    callable: Callable[..., ToolResult] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["callable"] = getattr(self.callable, "__name__", str(self.callable))
        return _clean(payload)


@dataclass
class HandoffRecord(JsonDataclass):
    from_agent: str
    to_agent: str
    reason: str
    state_keys_passed: list[str]
    timestamp: str = field(default_factory=utc_timestamp)
    handoff_status: str = "success"


@dataclass
class CriticVerdict(JsonDataclass):
    step_id: str
    agent_name: str
    verdict: str
    issues: list[str]
    reason: str
    suggested_next_action: str
    timestamp: str = field(default_factory=utc_timestamp)


@dataclass
class MultiAgentMemory(JsonDataclass):
    task_metadata: dict[str, Any] = field(default_factory=dict)
    selected_profile: str | None = None
    selected_domain_agent: str | None = None
    active_agents: list[str] = field(default_factory=list)
    executed_agents: list[str] = field(default_factory=list)
    executed_tools: list[str] = field(default_factory=list)
    handoff_records: list[dict[str, Any]] = field(default_factory=list)
    best_candidate_summary: dict[str, Any] = field(default_factory=dict)
    generated_candidate_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    suggested_next_actions: list[str] = field(default_factory=list)
    data_source: str = "real_simulation_csv"
    engineering_validity: str = "simulation_only"
