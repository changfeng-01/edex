from __future__ import annotations

from pathlib import Path

import pandas as pd

from goa_eval.product_demo.artifact_collector import ProductDemoArtifacts
from goa_eval.product_demo.schemas import ENGINEERING_VALIDITY, REPORT_FILES


def write_reports(
    artifacts: ProductDemoArtifacts,
    report_dir: Path,
    case_id: str,
    table_paths: dict[str, Path],
    figure_paths: dict[str, Path],
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "executive": report_dir / REPORT_FILES["executive"],
        "demo": report_dir / REPORT_FILES["demo"],
        "handoff": report_dir / REPORT_FILES["handoff"],
    }
    paths["executive"].write_text(_executive_summary(artifacts, case_id), encoding="utf-8")
    paths["demo"].write_text(_demo_report(artifacts, case_id, table_paths, figure_paths), encoding="utf-8")
    paths["handoff"].write_text(_handoff_notes(artifacts, case_id), encoding="utf-8")
    return paths


def _executive_summary(artifacts: ProductDemoArtifacts, case_id: str) -> str:
    return "\n".join(
        [
            f"# Executive Summary: {case_id}",
            "",
            f"- overall_status: {artifacts.summary.get('Overall_status') or artifacts.summary.get('overall_status', 'unknown')}",
            f"- overall_score: {artifacts.score.get('overall_score', 'unknown')}",
            f"- hard_constraint_passed: {artifacts.score.get('hard_constraint_passed', 'unknown')}",
            f"- validation_status: {artifacts.validation_status}",
            f"- candidate_status: {artifacts.candidate_status}",
            f"- data_source: {artifacts.evidence.get('data_source')}",
            f"- engineering_validity = {artifacts.evidence.get('engineering_validity', ENGINEERING_VALIDITY)}",
            "",
            "This package is a presentation layer over existing CircuitPilot artifacts. It does not claim physical validation, silicon validation, tape-out proof, or lab verification.",
            "",
        ]
    )


def _demo_report(
    artifacts: ProductDemoArtifacts,
    case_id: str,
    table_paths: dict[str, Path],
    figure_paths: dict[str, Path],
) -> str:
    constraints = _count_constraint_status(table_paths["constraints"])
    return "\n".join(
        [
            f"# Product Demo Report: {case_id}",
            "",
            "## Evidence Boundary",
            "",
            f"- data_source: {artifacts.evidence.get('data_source')}",
            f"- engineering_validity = {artifacts.evidence.get('engineering_validity', ENGINEERING_VALIDITY)}",
            f"- evidence_level: {artifacts.evidence.get('evidence_level')}",
            f"- simulation_backend: {artifacts.evidence.get('simulation_backend')}",
            f"- mock_used: {artifacts.evidence.get('mock_used')}",
            f"- pdk_available: {artifacts.evidence.get('pdk_available')}",
            f"- ngspice_available: {artifacts.evidence.get('ngspice_available')}",
            f"- reportable_as_real_ngspice: {artifacts.evidence.get('reportable_as_real_ngspice')}",
            f"- optimizer_claim_level: {artifacts.evidence.get('optimizer_claim_level')}",
            "",
            "## What To Read",
            "",
            f"- Run summary: `{table_paths['run_summary'].name}`",
            f"- Constraints: `{table_paths['constraints'].name}` ({constraints})",
            f"- Candidate ranking: `{table_paths['candidates'].name}`",
            f"- Before/after validation: `{table_paths['before_after'].name}`",
            "",
            "## Figures",
            "",
            *[f"- `{path.name}`" for path in figure_paths.values()],
            "",
            "## Validation State",
            "",
            f"`validation_status = {artifacts.validation_status}`. If this is `awaiting_rerun_results`, no after-run improvement is claimed.",
            "",
        ]
    )


def _handoff_notes(artifacts: ProductDemoArtifacts, case_id: str) -> str:
    missing = ", ".join(artifacts.missing_files) if artifacts.missing_files else "none"
    return "\n".join(
        [
            f"# Handoff Notes: {case_id}",
            "",
            "## How This Package Was Built",
            "",
            "Run from the repository root:",
            "",
            "```bash",
            f"python -m goa_eval.cli product-demo --input-dir {artifacts.input_dir.as_posix()} --output-dir outputs/product_demo --case-id {case_id}",
            "```",
            "",
            "## Missing Optional Inputs",
            "",
            f"- {missing}",
            "",
            "## Evidence Rules For Teammates",
            "",
            f"- Keep `engineering_validity = {artifacts.evidence.get('engineering_validity', ENGINEERING_VALIDITY)}` unless a source artifact explicitly provides another boundary.",
            "- Add rerun or validation artifacts before claiming improvement.",
            "- Do not add claims of physical validation, silicon validation, tape-out proof, or lab verification to this package.",
            "",
        ]
    )


def _count_constraint_status(path: Path) -> str:
    if not path.exists():
        return "constraint table unavailable"
    frame = pd.read_csv(path)
    if "status" not in frame:
        return "status column unavailable"
    counts = frame["status"].value_counts().to_dict()
    return ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
