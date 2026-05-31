from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.evidence import default_external_csv_evidence
from goa_eval.product_demo.schemas import (
    AWAITING_CANDIDATE_GENERATION,
    AWAITING_RERUN_RESULTS,
    AVAILABLE,
    DATA_SOURCE,
    ENGINEERING_VALIDITY,
    EVIDENCE_FIELDS,
    INPUT_ARTIFACT_NAMES,
)


@dataclass(frozen=True)
class ProductDemoArtifacts:
    input_dir: Path
    summary: dict[str, Any]
    score: dict[str, Any]
    manifest: dict[str, Any]
    analysis_metrics: dict[str, Any]
    metrics: pd.DataFrame
    candidates: pd.DataFrame
    validation: pd.DataFrame
    waveform: pd.DataFrame
    figure_manifest: dict[str, Any]
    files: dict[str, Path]
    missing_files: list[str]
    evidence: dict[str, Any]
    validation_status: str
    candidate_status: str


def collect_artifacts(input_dir: Path) -> ProductDemoArtifacts:
    input_dir = input_dir.resolve()
    files = _discover_files(input_dir)
    summary = _read_json(files.get("real_summary.json"))
    score = _read_json(files.get("score_summary.json"))
    manifest = _read_json(files.get("run_manifest_real.json"))
    analysis_metrics = _read_json(files.get("analysis_metrics.json"))
    figure_manifest = _read_json(files.get("figure_manifest.json"))
    metrics = _read_csv(files.get("real_metrics.csv"))
    candidates = _read_csv(files.get("best_next_candidates.csv"))
    if candidates.empty:
        candidates = _read_csv(files.get("next_candidates.csv"))
    if candidates.empty:
        candidates = _read_csv(files.get("optimization_leaderboard.csv"))
    validation = _read_csv(files.get("validation_summary.csv"))
    waveform = _read_csv(files.get("waveform.csv"))
    missing_files = [
        name for name in INPUT_ARTIFACT_NAMES if name not in files and not _has_fallback(name, files)
    ]
    validation_status = AVAILABLE if not validation.empty else AWAITING_RERUN_RESULTS
    candidate_status = AVAILABLE if not candidates.empty else AWAITING_CANDIDATE_GENERATION
    evidence = _collect_evidence(summary, score, manifest)
    return ProductDemoArtifacts(
        input_dir=input_dir,
        summary=summary,
        score=score,
        manifest=manifest,
        analysis_metrics=analysis_metrics,
        metrics=metrics,
        candidates=candidates,
        validation=validation,
        waveform=waveform,
        figure_manifest=figure_manifest,
        files=files,
        missing_files=missing_files,
        evidence=evidence,
        validation_status=validation_status,
        candidate_status=candidate_status,
    )


def write_input_snapshot(artifacts: ProductDemoArtifacts, output_dir: Path, case_id: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in INPUT_ARTIFACT_NAMES:
        path = artifacts.files.get(name)
        if path is None:
            rows.append({"name": name, "status": "missing", "relative_path": None, "size_bytes": None})
            continue
        rows.append(
            {
                "name": name,
                "status": "available",
                "relative_path": _display_path(path, artifacts.input_dir),
                "size_bytes": path.stat().st_size,
            }
        )
    figure_manifest = artifacts.files.get("figure_manifest.json")
    snapshot = {
        "case_id": case_id,
        "input_dir": str(artifacts.input_dir),
        "artifact_count": len(artifacts.files),
        "source_figure_manifest_available": bool(figure_manifest),
        "evidence": artifacts.evidence,
        "artifacts": rows,
    }
    path = output_dir / "input_artifact_manifest.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _discover_files(input_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name in INPUT_ARTIFACT_NAMES:
        path = input_dir / name
        if path.exists():
            files[name] = path
    figure_manifest = input_dir / "figures" / "figure_manifest.json"
    if figure_manifest.exists():
        files["figure_manifest.json"] = figure_manifest
    return files


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _collect_evidence(*payloads: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        **default_external_csv_evidence(),
    }
    for payload in payloads:
        for field in EVIDENCE_FIELDS:
            if field in payload and payload[field] not in (None, ""):
                evidence[field] = payload[field]
    evidence["data_source"] = evidence.get("data_source") or DATA_SOURCE
    evidence["engineering_validity"] = evidence.get("engineering_validity") or ENGINEERING_VALIDITY
    return evidence


def _has_fallback(name: str, files: dict[str, Path]) -> bool:
    if name == "next_candidates.csv":
        return "best_next_candidates.csv" in files or "optimization_leaderboard.csv" in files
    if name == "best_next_candidates.csv":
        return "next_candidates.csv" in files or "optimization_leaderboard.csv" in files
    if name == "optimization_leaderboard.csv":
        return "next_candidates.csv" in files or "best_next_candidates.csv" in files
    return False


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
