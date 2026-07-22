from goa_eval.multi_agent.agent_contracts import get_agent_contracts, is_tool_allowed


REQUIRED_AGENTS = {
    "SupervisorAgent",
    "RouterAgent",
    "GOAAgent",
    "GenericWaveformAgent",
    "NetlistAgent",
    "EvaluationAgent",
    "OptimizationAgent",
    "CriticAgent",
    "ReportAgent",
}


def test_all_required_agents_have_contracts():
    contracts = get_agent_contracts()

    assert REQUIRED_AGENTS <= set(contracts)
    for name in REQUIRED_AGENTS:
        contract = contracts[name]
        assert contract.agent_name == name
        assert contract.role
        assert contract.allowed_tools is not None
        assert contract.input_schema
        assert contract.output_schema
        assert contract.handoff_policy
        assert contract.failure_policy


def test_agent_tool_permissions_are_enforced():
    assert is_tool_allowed("RouterAgent", "inspect_task_inputs")
    assert not is_tool_allowed("RouterAgent", "generate_candidates")
    assert is_tool_allowed("OptimizationAgent", "generate_candidates")
