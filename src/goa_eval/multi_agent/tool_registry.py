from __future__ import annotations

from goa_eval.multi_agent import tools
from goa_eval.multi_agent.schemas import ToolMetadata


def get_tool_registry() -> dict[str, ToolMetadata]:
    return {
        "inspect_task_inputs": ToolMetadata(
            "inspect_task_inputs",
            "Check task input paths and classify available input types.",
            ["inputs"],
            "input_availability_summary",
            tools.inspect_task_inputs,
        ),
        "inspect_leaderboard": ToolMetadata(
            "inspect_leaderboard",
            "Read a leaderboard CSV and summarize the best candidate.",
            ["leaderboard_path"],
            "leaderboard_summary",
            tools.inspect_leaderboard,
        ),
        "inspect_score_summary": ToolMetadata(
            "inspect_score_summary",
            "Read score_summary.json and preserve boundary fields.",
            ["score_summary_path"],
            "score_summary",
            tools.inspect_score_summary,
        ),
        "inspect_real_metrics": ToolMetadata(
            "inspect_real_metrics",
            "Read real_metrics.csv and summarize metric anomalies.",
            ["real_metrics_path"],
            "metrics_summary",
            tools.inspect_real_metrics,
        ),
        "generate_candidates": ToolMetadata(
            "generate_candidates",
            "Generate next_candidates.csv through the existing optimizer wrapper.",
            ["leaderboard_path", "param_space_path", "output_dir", "max_candidates"],
            "candidate_generation_summary",
            tools.generate_candidates,
        ),
        "inspect_candidates": ToolMetadata(
            "inspect_candidates",
            "Inspect generated candidates for count, range, and parameter-change risk.",
            ["next_candidates_path", "param_space_path"],
            "candidate_risk_summary",
            tools.inspect_candidates,
        ),
        "check_schema_and_boundary": ToolMetadata(
            "check_schema_and_boundary",
            "Check schema markers and simulation-only boundary fields.",
            ["output_path", "expected_data_source", "expected_engineering_validity"],
            "boundary_check_summary",
            tools.check_schema_and_boundary,
        ),
        "write_multi_agent_report": ToolMetadata(
            "write_multi_agent_report",
            "Write the final local multi-agent decision report.",
            ["final_state", "memory", "trace", "handoff_trace", "critic_report", "output_dir"],
            "multi_agent_decision_report_path",
            tools.write_multi_agent_report,
        ),
    }
