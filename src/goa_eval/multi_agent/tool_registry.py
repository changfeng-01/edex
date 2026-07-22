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
        "inspect_artifact_bundle": ToolMetadata(
            "inspect_artifact_bundle",
            "Discover current evidence artifacts from task artifact directories.",
            ["inputs"],
            "artifact_bundle_summary",
            tools.inspect_artifact_bundle,
        ),
        "inspect_real_summary": ToolMetadata(
            "inspect_real_summary",
            "Read real_summary.json and summarize the evidence boundary and key metrics.",
            ["real_summary_path"],
            "real_summary",
            tools.inspect_real_summary,
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
        "inspect_analysis_metrics": ToolMetadata(
            "inspect_analysis_metrics",
            "Read analysis_metrics.json and summarize topology/profile metric coverage.",
            ["analysis_metrics_path"],
            "analysis_metrics_summary",
            tools.inspect_analysis_metrics,
        ),
        "inspect_optimization_history": ToolMetadata(
            "inspect_optimization_history",
            "Read optimization_history.json and summarize rounds, best score, best run, stop reason, and target status.",
            ["optimization_history_path"],
            "optimization_history_summary",
            tools.inspect_optimization_history,
        ),
        "inspect_optimization_leaderboard": ToolMetadata(
            "inspect_optimization_leaderboard",
            "Read optimization_leaderboard.csv as the existing optimization leaderboard.",
            ["optimization_leaderboard_path"],
            "optimization_leaderboard_summary",
            tools.inspect_optimization_leaderboard,
        ),
        "inspect_validation_summary": ToolMetadata(
            "inspect_validation_summary",
            "Read validation_summary.csv and summarize failed validation targets.",
            ["validation_summary_path"],
            "validation_summary",
            tools.inspect_validation_summary,
        ),
        "inspect_run_manifest": ToolMetadata(
            "inspect_run_manifest",
            "Read run_manifest_real.json and preserve run boundary fields.",
            ["run_manifest_path"],
            "run_manifest_summary",
            tools.inspect_run_manifest,
        ),
        "inspect_existing_reports": ToolMetadata(
            "inspect_existing_reports",
            "Inspect existing Markdown evidence reports for presence and forbidden claims.",
            ["inputs"],
            "existing_report_summary",
            tools.inspect_existing_reports,
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
        "inspect_netlist_integrity": ToolMetadata(
            "inspect_netlist_integrity",
            "Inspect a SPICE netlist for minimal completeness and parser-visible device evidence.",
            ["netlist_path"],
            "netlist_integrity_summary",
            tools.inspect_netlist_integrity,
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
