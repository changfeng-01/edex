from __future__ import annotations

import importlib.util


LANGGRAPH_REQUIRED_MESSAGE = (
    "LangGraph is required for multi-agent-run. Please install the agent extra "
    "or use the existing deterministic CLI commands directly."
)


def check_langgraph_availability() -> dict[str, object]:
    spec = importlib.util.find_spec("langgraph")
    if spec is None:
        return {
            "available": False,
            "message": LANGGRAPH_REQUIRED_MESSAGE,
            "install_hint": 'python -m pip install -e ".[test,agent]"',
        }
    return {
        "available": True,
        "message": "LangGraph is available.",
        "install_hint": 'python -m pip install -e ".[test,agent]"',
        "module_path": spec.origin,
    }
