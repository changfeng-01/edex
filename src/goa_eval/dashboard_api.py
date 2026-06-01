from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from goa_eval.demo_mainline import run_demo_mainline
from goa_eval.product_demo.schemas import DIRECTORIES

import json


def create_app(
    *,
    product_demo_root: Path | str = Path("outputs/product_demo"),
    enable_build_api: bool | None = None,
) -> FastAPI:
    root = Path(product_demo_root)
    build_enabled = _env_enabled("CIRCUITPILOT_ENABLE_BUILD_API") if enable_build_api is None else enable_build_api
    app = FastAPI(title="CircuitPilot Dashboard API")

    @app.get("/api/cases/{case_id}/bundle")
    def get_case_bundle(case_id: str) -> dict[str, Any]:
        return load_dashboard_bundle(root / case_id, case_id)

    @app.get("/api/cases/{case_id}/files/{category}/{filename:path}")
    def get_case_file(case_id: str, category: str, filename: str) -> FileResponse:
        case_dir = (root / case_id).resolve()
        subdir_name = {"figures": DIRECTORIES["figures"], "reports": DIRECTORIES["report"]}.get(category)
        if subdir_name is None:
            raise HTTPException(status_code=404, detail="Unknown file category")
        base = (case_dir / subdir_name).resolve()
        target = (base / filename).resolve()
        if not _is_relative_to(target, base) or not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)

    @app.post("/api/build")
    def build_demo(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not build_enabled:
            raise HTTPException(status_code=403, detail="Build API is disabled by default")
        payload = payload or {}
        manifest = run_demo_mainline(case_id=str(payload.get("case_id") or "public_demo"), product_demo_root=root)
        return {"status": "ok", "manifest": manifest}

    return app


def load_dashboard_bundle(case_dir: Path, case_id: str) -> dict[str, Any]:
    dashboard_dir = case_dir / DIRECTORIES["dashboard"]
    if not dashboard_dir.exists():
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    summary = _read_json(dashboard_dir / "dashboard_summary.json")
    tables = _read_json(dashboard_dir / "dashboard_tables.json")
    figures_payload = _read_json(dashboard_dir / "dashboard_figures.json")
    manifest = _read_json(dashboard_dir / "presentation_manifest.json")
    base_path = f"/api/cases/{case_id}"
    return {
        "caseId": case_id,
        "basePath": base_path,
        "summary": summary,
        "tables": tables,
        "figures": _build_figures(base_path, figures_payload, manifest),
        "manifest": manifest,
        "reports": _build_reports(base_path, case_dir, manifest),
        "resourceErrors": [],
    }


def _build_figures(base_path: str, figures_payload: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    figure_names = manifest.get("figures", {}) if isinstance(manifest.get("figures"), dict) else {}
    keys = list(figure_names) or list(figures_payload)
    figures = []
    for key in keys:
        payload = figures_payload.get(key, {}) if isinstance(figures_payload.get(key), dict) else {}
        file = payload.get("file") or figure_names.get(key)
        if not file:
            continue
        figures.append(
            {
                "key": key,
                "file": file,
                "title": payload.get("title") or key.replace("_", " ").title(),
                "size_bytes": payload.get("size_bytes"),
                "source_manifest_available": payload.get("source_manifest_available"),
                "url": f"{base_path}/files/figures/{file}",
            }
        )
    return figures


def _build_reports(base_path: str, case_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    report_files = manifest.get("reports") if isinstance(manifest.get("reports"), list) else []
    reports = []
    for file in report_files:
        file_name = str(file)
        path = case_dir / DIRECTORIES["report"] / file_name
        reports.append(
            {
                "file": file_name,
                "title": _title_from_file(file_name),
                "url": f"{base_path}/files/reports/{file_name}",
                "content": path.read_text(encoding="utf-8") if path.exists() else None,
            }
        )
    return reports


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _title_from_file(file: str) -> str:
    stem = file.removesuffix(".md")
    return " ".join(part.capitalize() for part in stem.replace("-", "_").split("_") if part)


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
