from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_FILENAMES = {
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
    "sky130_mainline_report": "sky130_mainline_report.md",
}
ARTIFACT_DIR_KEYS = ("artifact_dir", "run_dir", "baseline_run_dir", "sky130_mainline_dir", "optimization_dir")


def build_evidence_index(inputs: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, Any]:
    raw_inputs = dict(inputs or {})
    search_dirs = _search_dirs(raw_inputs)
    artifacts = {}
    for artifact_key, filename in ARTIFACT_FILENAMES.items():
        path, source = _resolve_artifact(artifact_key, filename, raw_inputs, search_dirs)
        artifacts[artifact_key] = {
            "filename": filename,
            "path": str(path) if path else None,
            "exists": bool(path and path.exists()),
            "source": source,
            "kind": _artifact_kind(filename),
        }

    discovered_count = sum(1 for item in artifacts.values() if item["exists"])
    index = {
        "schema_version": "1.0",
        "result_version": "1.0",
        "artifacts": artifacts,
        "aliases": _aliases(raw_inputs, artifacts),
        "search_dirs": [str(path) for path in search_dirs],
        "raw_inputs": {str(key): str(value) for key, value in raw_inputs.items()},
        "artifact_discovery_score": discovered_count / len(ARTIFACT_FILENAMES),
        "missing_optional_artifacts": [key for key, item in artifacts.items() if not item["exists"]],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }
    if output_dir is not None:
        index["output_path"] = str(Path(output_dir) / "evidence_index.json")
    return index


def write_evidence_index(index: dict[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "evidence_index.json"
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def paths_from_evidence_index(index: dict[str, Any]) -> dict[str, str]:
    paths = {}
    for key, item in (index.get("artifacts") or {}).items():
        if item.get("exists") and item.get("path"):
            paths[key] = str(item["path"])
    for key, path in (index.get("aliases") or {}).items():
        if path:
            paths[key] = str(path)
    return paths


def evidence_path(index: dict[str, Any], key: str) -> str | None:
    aliases = index.get("aliases") or {}
    if aliases.get(key):
        return str(aliases[key])
    item = (index.get("artifacts") or {}).get(key) or {}
    if item.get("exists") and item.get("path"):
        return str(item["path"])
    return None


def _search_dirs(inputs: dict[str, Any]) -> list[Path]:
    dirs = []
    for key in ARTIFACT_DIR_KEYS:
        value = inputs.get(key)
        if value:
            path = Path(str(value))
            if path.exists() and path.is_dir() and path not in dirs:
                dirs.append(path)
    return dirs


def _resolve_artifact(
    artifact_key: str, filename: str, inputs: dict[str, Any], search_dirs: list[Path]
) -> tuple[Path | None, str]:
    explicit = inputs.get(artifact_key)
    if explicit:
        return Path(str(explicit)), f"input:{artifact_key}"
    if artifact_key == "optimization_leaderboard" and inputs.get("leaderboard"):
        return Path(str(inputs["leaderboard"])), "input:leaderboard"
    if artifact_key in {"next_candidates", "best_next_candidates"} and inputs.get("next_candidates"):
        return Path(str(inputs["next_candidates"])), "input:next_candidates"
    for directory in search_dirs:
        candidate = directory / filename
        if candidate.exists():
            return candidate, f"dir:{directory}"
    return None, "missing"


def _aliases(inputs: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if inputs.get("leaderboard"):
        aliases["leaderboard"] = str(inputs["leaderboard"])
    elif artifacts["optimization_leaderboard"]["exists"]:
        aliases["leaderboard"] = str(artifacts["optimization_leaderboard"]["path"])
    if inputs.get("next_candidates"):
        aliases["next_candidates"] = str(inputs["next_candidates"])
    elif artifacts["best_next_candidates"]["exists"]:
        aliases["next_candidates"] = str(artifacts["best_next_candidates"]["path"])
    elif artifacts["next_candidates"]["exists"]:
        aliases["next_candidates"] = str(artifacts["next_candidates"]["path"])
    return aliases


def _artifact_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix == ".md":
        return "markdown"
    return "unknown"
