from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.product_demo.artifact_collector import ProductDemoArtifacts
from goa_eval.product_demo.schemas import DASHBOARD_FILES


def write_dashboard_exports(
    artifacts: ProductDemoArtifacts,
    dashboard_dir: Path,
    case_id: str,
    table_paths: dict[str, Path],
    figure_paths: dict[str, Path],
) -> dict[str, Path]:
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": dashboard_dir / DASHBOARD_FILES["summary"],
        "tables": dashboard_dir / DASHBOARD_FILES["tables"],
        "figures": dashboard_dir / DASHBOARD_FILES["figures"],
        "manifest": dashboard_dir / DASHBOARD_FILES["manifest"],
    }
    summary_payload = {
        "case_id": case_id,
        "run_id": artifacts.summary.get("run_id") or artifacts.manifest.get("run_id") or case_id,
        "overall_status": artifacts.summary.get("Overall_status") or artifacts.summary.get("overall_status"),
        "overall_score": artifacts.score.get("overall_score"),
        "hard_constraint_passed": artifacts.score.get("hard_constraint_passed"),
        "validation_status": artifacts.validation_status,
        "candidate_status": artifacts.candidate_status,
        "evidence": artifacts.evidence,
    }
    tables_payload = {
        key: {
            "file": path.name,
            "rows": _read_table(path),
        }
        for key, path in table_paths.items()
    }
    figures_payload = {
        key: {
            "file": path.name,
            "title": _title_from_key(key),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "source_manifest_available": bool(artifacts.figure_manifest),
        }
        for key, path in figure_paths.items()
    }
    manifest_payload = {
        "case_id": case_id,
        "package_version": "1.0",
        "input_dir": str(artifacts.input_dir),
        "validation_status": artifacts.validation_status,
        "candidate_status": artifacts.candidate_status,
        "evidence": artifacts.evidence,
        "tables": {key: path.name for key, path in table_paths.items()},
        "figures": {key: path.name for key, path in figure_paths.items()},
        "reports": [
            "executive_summary.md",
            "demo_report.md",
            "handoff_notes.md",
        ],
    }
    _write_json(paths["summary"], summary_payload)
    _write_json(paths["tables"], tables_payload)
    _write_json(paths["figures"], figures_payload)
    _write_json(paths["manifest"], manifest_payload)
    return paths


def _read_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return _json_safe(pd.read_csv(path).to_dict(orient="records"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if pd.isna(value) if not isinstance(value, (str, list, dict, tuple)) else False:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _title_from_key(key: str) -> str:
    return key.replace("_", " ").title()
