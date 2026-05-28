from __future__ import annotations

from pathlib import Path

from goa_eval.multi_agent.agents._utils import add_message
from goa_eval.multi_agent.trace import record_step


def run_supervisor_agent(state: dict) -> dict:
    state["active_agent"] = "SupervisorAgent"
    state["next_agent"] = "RouterAgent"
    add_message(
        state,
        "SupervisorAgent",
        {
            "summary": "Initialized local multi-agent run.",
            "data_source": state.get("data_source"),
            "engineering_validity": state.get("engineering_validity"),
        },
    )
    plan_path = Path(state["output_dir"]) / "multi_agent_plan.json"
    state.setdefault("generated_files", {})["multi_agent_plan"] = str(plan_path)
    record_step(
        state,
        agent_name="SupervisorAgent",
        node_name="supervisor",
        step_id="supervisor-1",
        status="pass",
        reason="shared state initialized",
        output_summary={"next_agent": "RouterAgent"},
    )
    return state
