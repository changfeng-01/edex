from __future__ import annotations

from pathlib import Path
from typing import Any


CURRENT_MAIN_ARTIFACTS = {
    "real_summary": "real_summary.json",
    "real_metrics": "real_metrics.csv",
    "score_summary": "score_summary.json",
    "analysis_metrics": "analysis_metrics.json",
    "diagnosis_report": "diagnosis_report.md",
    "real_waveform_report": "real_waveform_report.md",
    "next_candidates": "next_candidates.csv",
    "best_next_candidates": "best_next_candidates.csv",
    "optimization_history": "optimization_history.json",
    "optimization_leaderboard": "optimization_leaderboard.csv",
    "validation_summary": "validation_summary.csv",
    "run_manifest_real": "run_manifest_real.json",
}

ARTIFACT_DIR_KEYS = {"artifact_dir", "run_dir", "baseline_run_dir", "optimization_dir"}


def normalize_artifact_inputs(inputs: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, Any]:
    normalized = dict(inputs or {})
    for key in list(ARTIFACT_DIR_KEYS):
        value = normalized.get(key)
        if value:
            add_artifacts_from_dir(normalized, Path(str(value)))
    if output_dir and not any(key in normalized for key in CURRENT_MAIN_ARTIFACTS):
        add_artifacts_from_dir(normalized, Path(output_dir))
    if "optimization_leaderboard" in normalized and "leaderboard" not in normalized:
        normalized["leaderboard"] = normalized["optimization_leaderboard"]
    if "best_next_candidates" in normalized and "next_candidates" not in normalized:
        normalized["next_candidates"] = normalized["best_next_candidates"]
    return normalized


def add_artifacts_from_dir(inputs: dict[str, Any], artifact_dir: Path) -> None:
    for key, filename in CURRENT_MAIN_ARTIFACTS.items():
        path = artifact_dir / filename
        if path.exists() and key not in inputs:
            inputs[key] = str(path)
