from __future__ import annotations

from typing import Any, Mapping

DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"
MUST_RESIMULATE = True

BOUNDARY_FIELDS = ("data_source", "engineering_validity", "must_resimulate")


def default_evidence_boundary() -> dict[str, Any]:
    return {
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
    }


def normalize_evidence_boundary(
    evidence: Mapping[str, Any] | None = None,
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(evidence or {})
    if override:
        normalized.update({key: value for key, value in override.items() if value not in (None, "")})
    normalized.update(default_evidence_boundary())
    return normalized

AWAITING_RERUN_RESULTS = "awaiting_rerun_results"
AWAITING_CANDIDATE_GENERATION = "awaiting_candidate_generation"
AVAILABLE = "available"

EVIDENCE_FIELDS = [
    "data_source",
    "engineering_validity",
    "must_resimulate",
    "evidence_level",
    "simulation_backend",
    "mock_used",
    "optimizer_claim_level",
]

DIRECTORIES = {
    "input_snapshot": "01_input_snapshot",
    "evaluation": "02_evaluation",
    "candidates": "03_candidates",
    "validation": "04_validation",
    "figures": "05_figures",
    "dashboard": "06_dashboard_data",
    "report": "07_report",
}

TABLE_FILES = {
    "run_summary": "run_summary_table.csv",
    "constraints": "constraint_table.csv",
    "candidates": "top_candidates_table.csv",
    "before_after": "before_after_table.csv",
}

FIGURE_FILES = {
    "waveform": "fig01_waveform_overview.png",
    "constraints": "fig02_constraint_status.png",
    "metrics": "fig03_metric_comparison.png",
    "candidates": "fig04_candidate_ranking.png",
    "before_after": "fig05_before_after_comparison.png",
    "evidence": "fig06_evidence_card.png",
}

DASHBOARD_FILES = {
    "summary": "dashboard_summary.json",
    "tables": "dashboard_tables.json",
    "figures": "dashboard_figures.json",
    "manifest": "presentation_manifest.json",
}

REPORT_FILES = {
    "executive": "executive_summary.md",
    "demo": "demo_report.md",
    "handoff": "handoff_notes.md",
}

RUN_SUMMARY_COLUMNS = [
    "case_id",
    "run_id",
    "overall_status",
    "overall_score",
    "hard_constraint_passed",
    "stage_count",
    "resolved_output_node_count",
    "data_source",
    "engineering_validity",
    "evidence_level",
    "simulation_backend",
    "optimizer_claim_level",
    "validation_status",
    "candidate_status",
]

CONSTRAINT_COLUMNS = [
    "constraint",
    "status",
    "current_value",
    "threshold",
    "reason",
]

CANDIDATE_COLUMNS = [
    "rank",
    "candidate_id",
    "priority",
    "parameter_changes",
    "trigger_metric",
    "strategy",
    "search_score",
    "status",
    "data_source",
    "engineering_validity",
]

BEFORE_AFTER_COLUMNS = [
    "metric",
    "before_value",
    "after_value",
    "delta",
    "status",
    "unit",
]

INPUT_ARTIFACT_NAMES = [
    "real_summary.json",
    "score_summary.json",
    "real_metrics.csv",
    "analysis_metrics.json",
    "diagnosis_report.md",
    "real_waveform_report.md",
    "next_candidates.csv",
    "best_next_candidates.csv",
    "optimization_leaderboard.csv",
    "validation_summary.csv",
    "run_manifest_real.json",
    "waveform.csv",
]
