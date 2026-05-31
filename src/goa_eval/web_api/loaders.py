from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from goa_eval.product_demo.schemas import DASHBOARD_FILES, DIRECTORIES, ENGINEERING_VALIDITY, TABLE_FILES
from goa_eval.web_api.security import ALLOWED_FIGURE_EXTENSIONS, CASE_ID_RE, resolve_case_dir


def list_cases(root: Path) -> dict[str, list[dict[str, Any]]]:
    if not root.exists() or not root.is_dir():
        return {"cases": []}
    cases = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if not CASE_ID_RE.fullmatch(case_dir.name) or case_dir.name in {".", ".."}:
            continue
        dashboard_dir = case_dir / DIRECTORIES["dashboard"]
        summary_path = dashboard_dir / DASHBOARD_FILES["summary"]
        manifest_path = dashboard_dir / DASHBOARD_FILES["manifest"]
        metadata = _read_json(summary_path)[0] or _read_json(manifest_path)[0] or {}
        cases.append(
            {
                "case_id": case_dir.name,
                "path": _display_path(case_dir),
                "has_manifest": manifest_path.exists(),
                "has_summary": summary_path.exists(),
                "validation_status": metadata.get("validation_status", "unknown"),
                "candidate_status": metadata.get("candidate_status", "unknown"),
            }
        )
    return {"cases": cases}


def load_summary(root: Path, case_id: str) -> dict[str, Any]:
    case_dir = resolve_case_dir(root, case_id)
    path = case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["summary"]
    payload, message = _read_json(path)
    if isinstance(payload, dict):
        return payload
    return _missing_summary(case_id, message or f"{DASHBOARD_FILES['summary']} not found")


def load_tables(root: Path, case_id: str) -> dict[str, Any]:
    case_dir = resolve_case_dir(root, case_id)
    dashboard_path = case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["tables"]
    payload, _message = _read_json(dashboard_path)
    if isinstance(payload, dict):
        return payload
    return {
        key: _load_csv_table(case_dir / table_dir / filename, filename)
        for key, table_dir, filename in _table_sources()
    }


def load_figures(root: Path, case_id: str) -> dict[str, list[dict[str, Any]]]:
    case_dir = resolve_case_dir(root, case_id)
    figures_dir = case_dir / DIRECTORIES["figures"]
    dashboard_path = case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["figures"]
    payload, _message = _read_json(dashboard_path)
    figures: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            filename = str(value.get("file", ""))
            path = _safe_figure_path(figures_dir, filename)
            figures.append(_figure_info(case_id, str(key), value.get("title"), path, filename))
    else:
        for path in sorted(figures_dir.glob("*")):
            if path.is_file() and path.suffix.lower() in ALLOWED_FIGURE_EXTENSIONS:
                figures.append(_figure_info(case_id, path.stem, None, path, path.name))
    return {"figures": figures}


def load_reports(root: Path, case_id: str) -> dict[str, list[dict[str, Any]]]:
    case_dir = resolve_case_dir(root, case_id)
    report_dir = case_dir / DIRECTORIES["report"]
    reports = [
        {
            "name": path.name,
            "url": f"/api/cases/{case_id}/reports/{path.name}",
            "exists": path.exists(),
        }
        for path in sorted(report_dir.glob("*.md"))
        if path.is_file()
    ]
    return {"reports": reports}


def load_manifest(root: Path, case_id: str) -> dict[str, Any]:
    case_dir = resolve_case_dir(root, case_id)
    path = case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["manifest"]
    payload, message = _read_json(path)
    if isinstance(payload, dict):
        return payload
    return {"case_id": case_id, "missing": True, "message": message or f"{DASHBOARD_FILES['manifest']} not found"}


def load_bundle(root: Path, case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "summary": load_summary(root, case_id),
        "tables": load_tables(root, case_id),
        "figures": load_figures(root, case_id)["figures"],
        "reports": load_reports(root, case_id)["reports"],
        "manifest": load_manifest(root, case_id),
    }


def _table_sources() -> list[tuple[str, str, str]]:
    return [
        ("run_summary", DIRECTORIES["evaluation"], TABLE_FILES["run_summary"]),
        ("constraints", DIRECTORIES["evaluation"], TABLE_FILES["constraints"]),
        ("candidates", DIRECTORIES["candidates"], TABLE_FILES["candidates"]),
        ("before_after", DIRECTORIES["validation"], TABLE_FILES["before_after"]),
    ]


def _load_csv_table(path: Path, filename: str) -> dict[str, Any]:
    if not path.exists():
        return {"file": filename, "rows": [], "missing": True, "message": f"{filename} not found"}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except Exception as exc:
        return {"file": filename, "rows": [], "missing": True, "message": f"{filename} could not be parsed: {exc}"}
    return {"file": filename, "rows": rows}


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, f"{path.name} not found"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"{path.name} could not be parsed: {exc}"


def _missing_summary(case_id: str, message: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "missing": True,
        "message": message,
        "validation_status": "unknown",
        "candidate_status": "unknown",
        "evidence": {
            "engineering_validity": ENGINEERING_VALIDITY,
        },
    }


def _figure_info(case_id: str, key: str, title: Any, path: Path, filename: str) -> dict[str, Any]:
    exists = bool(filename) and path.exists() and path.is_file()
    return {
        "key": key,
        "title": str(title) if title else key.replace("_", " ").title(),
        "file": filename,
        "url": f"/api/cases/{case_id}/figures/{filename}",
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
    }


def _safe_figure_path(figures_dir: Path, filename: str) -> Path:
    candidate = Path(filename)
    if (
        not filename
        or candidate.name != filename
        or candidate.is_absolute()
        or ".." in filename
        or candidate.suffix.lower() not in ALLOWED_FIGURE_EXTENSIONS
    ):
        return figures_dir / "__invalid_figure_filename__"
    return figures_dir / filename


def _display_path(path: Path) -> str:
    return path.as_posix()
