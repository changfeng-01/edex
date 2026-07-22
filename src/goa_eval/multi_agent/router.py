from __future__ import annotations

from goa_eval.multi_agent.domain_registry import default_domain_agent_registry


def route_task(task_type: str, profile: str, inputs: dict) -> dict[str, str]:
    return default_domain_agent_registry().resolve(task_type, profile, inputs)
