from goa_eval.multi_agent.tool_registry import get_tool_registry


REQUIRED_TOOLS = {
    "inspect_task_inputs",
    "inspect_leaderboard",
    "inspect_score_summary",
    "inspect_real_metrics",
    "generate_candidates",
    "inspect_candidates",
    "inspect_netlist_integrity",
    "check_schema_and_boundary",
    "write_multi_agent_report",
}


def test_required_tools_are_registered_with_metadata():
    registry = get_tool_registry()

    assert REQUIRED_TOOLS <= set(registry)
    for tool_name in REQUIRED_TOOLS:
        tool = registry[tool_name]
        assert tool.tool_name == tool_name
        assert tool.description
        assert tool.input_requirements
        assert tool.output_description
        assert callable(tool.callable)
