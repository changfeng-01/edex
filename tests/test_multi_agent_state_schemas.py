import json

from goa_eval.multi_agent.schemas import (
    AgentContract,
    CriticVerdict,
    HandoffRecord,
    MultiAgentMemory,
    MultiAgentTask,
    ToolResult,
)
from goa_eval.multi_agent.state import MultiAgentEDAState, new_state_from_task


def test_multi_agent_structures_are_json_serializable():
    task = MultiAgentTask(
        task_name="sky130_test",
        task_type="sky130_eda_optimization",
        profile="sky130_inverter_chain",
        inputs={"leaderboard": "leaderboard.csv"},
        objectives={"primary": "pass_hard_constraints"},
        validity={"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"},
    )
    contract = AgentContract(
        agent_name="RouterAgent",
        role="router",
        description="route task",
        allowed_tools=["inspect_task_inputs"],
        input_schema=["task"],
        output_schema=["selected_domain_agent"],
        handoff_policy={"next": ["GOAAgent"]},
        failure_policy={"on_unsupported_profile": "handoff_to_CriticAgent"},
        memory_scope="run_local",
    )
    tool = ToolResult(tool_name="inspect_task_inputs", status="pass", data={"ok": True})
    handoff = HandoffRecord("RouterAgent", "SKY130Agent", "profile match", ["profile"])
    verdict = CriticVerdict("step-1", "CriticAgent", "pass", [], "ok", "continue")
    memory = MultiAgentMemory(task_metadata={"task_name": task.task_name})
    state = MultiAgentEDAState(**new_state_from_task(task, "out"))

    payload = [task, contract, tool, handoff, verdict, memory, state]
    encoded = json.dumps([item.to_dict() for item in payload], ensure_ascii=False)

    assert "sky130_test" in encoded
    assert "simulation_only" in encoded
