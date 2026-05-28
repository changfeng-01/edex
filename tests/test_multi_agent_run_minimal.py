import subprocess
import sys
from pathlib import Path

import pytest

from goa_eval.multi_agent.availability import check_langgraph_availability


def test_multi_agent_run_cli_has_clear_langgraph_behavior(tmp_path):
    output_dir = tmp_path / "multi_agent"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "multi-agent-run",
            "--task",
            "examples/tasks/sky130_multi_agent_task.yaml",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    availability = check_langgraph_availability()
    if not availability["available"]:
        assert result.returncode == 2
        assert "LangGraph is required for multi-agent-run" in (result.stderr + result.stdout)
        return

    assert result.returncode == 0, result.stderr
    for name in [
        "multi_agent_plan.json",
        "multi_agent_trace.jsonl",
        "multi_agent_handoff_trace.jsonl",
        "critic_report.json",
        "multi_agent_memory.json",
        "multi_agent_decision_report.md",
        "optimization_loop_record.json",
        "optimization_decision_card.md",
    ]:
        path = output_dir / name
        assert path.exists()
        assert path.stat().st_size > 0


@pytest.mark.skipif(not check_langgraph_availability()["available"], reason="LangGraph not installed")
def test_minimal_run_routes_sky130_when_langgraph_available(tmp_path):
    from goa_eval.multi_agent.graph_app import run_multi_agent_task

    output_dir = tmp_path / "run"
    final_state = run_multi_agent_task(Path("examples/tasks/sky130_multi_agent_task.yaml"), output_dir)

    assert final_state["selected_domain_agent"] == "SKY130Agent"
    assert final_state["routing_reason"]
    assert (output_dir / "multi_agent_decision_report.md").exists()

    plan_text = (output_dir / "multi_agent_plan.json").read_text(encoding="utf-8")
    assert "routing_reason" in plan_text
    assert "agent_contracts" in plan_text
    assert "SKY130Agent" in plan_text
    assert (output_dir / "optimization_loop_record.json").exists()
    assert "awaiting_rerun_results" in (output_dir / "optimization_loop_record.json").read_text(encoding="utf-8")
    critic_text = (output_dir / "critic_report.json").read_text(encoding="utf-8")
    assert "risk_summary" in critic_text
    assert "top_risks" in critic_text
