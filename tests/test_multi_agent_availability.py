from goa_eval.multi_agent.availability import check_langgraph_availability


def test_langgraph_availability_returns_structured_status():
    status = check_langgraph_availability()

    assert {"available", "message", "install_hint"} <= set(status)
    if not status["available"]:
        assert "LangGraph is required for multi-agent-run" in status["message"]
