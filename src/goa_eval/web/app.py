from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.datastructures import FormData, UploadFile

from goa_eval.product_demo.schemas import DASHBOARD_FILES, DIRECTORIES
from goa_eval.web.runners import run_uploaded_case
from goa_eval.web.schemas import WebApiSettings, evidence_boundary
from goa_eval.web.storage import build_config, prepare_case_dir, read_status, resolve_asset, resolve_under, save_uploads, validate_case_id


def create_app(settings: WebApiSettings | None = None) -> FastAPI:
    settings = settings or WebApiSettings.from_env()
    app = FastAPI(title="CircuitPilot Upload API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "circuitpilot-upload-api"}

    @app.post("/api/cases")
    async def create_case(request: Request) -> dict[str, Any]:
        form = await request.form()
        fields = _form_fields(form)
        config = build_config(fields)
        uploads = _form_uploads(form)
        if not uploads:
            raise HTTPException(status_code=400, detail="waveform.csv is required")
        case_dir = prepare_case_dir(settings.web_cases_root, config.case_id)
        await save_uploads(case_dir, uploads)
        result = run_uploaded_case(case_dir, config)
        if result.status == "failed":
            return result.model_dump()
        return result.model_dump()

    @app.get("/api/cases/{case_id}/status")
    def case_status(case_id: str) -> dict[str, Any]:
        return read_status(settings.web_cases_root, case_id)

    @app.get("/api/cases/{case_id}/bundle")
    def case_bundle(case_id: str) -> dict[str, Any]:
        case_id = validate_case_id(case_id)
        case_dir = resolve_under(settings.web_cases_root, case_id, "product_demo", case_id)
        if not case_dir.exists():
            raise HTTPException(status_code=404, detail="case bundle not found")
        summary = _read_json(case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["summary"])
        tables = _read_json(case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["tables"])
        figures = _figure_infos(case_id, case_dir)
        reports = _report_infos(case_id, case_dir)
        manifest = _read_json(case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["manifest"])
        _attach_boundary(summary)
        _attach_boundary(manifest)
        return {
            "case_id": case_id,
            "summary": summary,
            "tables": tables,
            "figures": figures,
            "reports": reports,
            "manifest": manifest,
        }

    @app.get("/api/cases/{case_id}/assets/{asset_path:path}")
    def case_asset(case_id: str, asset_path: str) -> Response:
        path = resolve_asset(settings.web_cases_root, case_id, asset_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() == ".md":
            return Response(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")
        return FileResponse(path, media_type=media_type)

    return app


def _form_fields(form: FormData) -> dict[str, Any]:
    return {key: value for key, value in form.multi_items() if not isinstance(value, UploadFile)}


def _form_uploads(form: FormData) -> list[UploadFile]:
    uploads: list[UploadFile] = []
    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            setattr(value, "name", key)
            uploads.append(value)
    return uploads


def _figure_infos(case_id: str, case_dir: Path) -> list[dict[str, Any]]:
    dashboard_payload = _read_json(case_dir / DIRECTORIES["dashboard"] / DASHBOARD_FILES["figures"])
    figures_dir = case_dir / DIRECTORIES["figures"]
    figures: list[dict[str, Any]] = []
    for key, details in dashboard_payload.items():
        if not isinstance(details, dict):
            continue
        file = str(details.get("file") or "")
        path = figures_dir / file
        asset_path = f"product_demo/{case_id}/{DIRECTORIES['figures']}/{file}"
        figures.append(
            {
                "key": key,
                "title": details.get("title") or key.replace("_", " ").title(),
                "file": file,
                "url": f"/api/cases/{case_id}/assets/{asset_path}",
                "exists": path.exists() and path.is_file(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
                "source_manifest_available": details.get("source_manifest_available", False),
            }
        )
    return figures


def _report_infos(case_id: str, case_dir: Path) -> list[dict[str, Any]]:
    report_dir = case_dir / DIRECTORIES["report"]
    reports = []
    for path in sorted(report_dir.glob("*.md")):
        asset_path = f"product_demo/{case_id}/{DIRECTORIES['report']}/{path.name}"
        reports.append(
            {
                "name": path.name,
                "file": path.name,
                "title": path.stem.replace("_", " ").title(),
                "url": f"/api/cases/{case_id}/assets/{asset_path}",
                "exists": True,
            }
        )
    return reports


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _attach_boundary(payload: dict[str, Any]) -> None:
    evidence = dict(payload.get("evidence", {}))
    evidence.update(evidence_boundary())
    payload["evidence"] = evidence


app = create_app()
