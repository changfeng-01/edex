from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.datastructures import FormData, UploadFile

from goa_eval.io_utils import write_json
from goa_eval.product_demo.schemas import DIRECTORIES
from goa_eval.web.input_inspector import inspect_uploaded_case_input
from goa_eval.web_api.loaders import load_bundle
from goa_eval.web.runners import run_uploaded_case
from goa_eval.web.schemas import UploadedCaseConfig, WebApiSettings, evidence_boundary
from goa_eval.web.storage import (
    build_config,
    copy_sample_inputs,
    generate_demo_case_id,
    prepare_case_dir,
    read_status,
    resolve_asset,
    resolve_under,
    save_uploads,
    validate_case_id,
)


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
        result = await _run_case_from_uploads(settings, config, uploads)
        return result.model_dump()

    @app.post("/api/cases/preview")
    async def preview_case(request: Request) -> dict[str, Any]:
        form = await request.form()
        fields = _form_fields(form)
        config = build_config(fields)
        uploads = _form_uploads(form)
        if not uploads:
            raise HTTPException(status_code=400, detail="waveform.csv is required")
        case_dir = prepare_case_dir(settings.web_cases_root, config.case_id)
        await save_uploads(case_dir, uploads)
        preview = inspect_uploaded_case_input(case_dir, config)
        status = "preview_ready" if preview.get("ready_for_analysis") else "preview_failed"
        payload = {
            "case_id": config.case_id,
            "status": status,
            "preview": preview,
            "evidence_boundary": evidence_boundary(),
        }
        write_json(case_dir / "input_preview.json", payload)
        return payload

    @app.post("/api/demo/sample-case")
    def create_sample_case() -> dict[str, Any]:
        case_id = generate_demo_case_id()
        case_dir = prepare_case_dir(settings.web_cases_root, case_id)
        copy_sample_inputs(case_dir, Path("examples/sample_waveform.csv"), Path("examples/sample_params.yaml"))
        result = run_uploaded_case(case_dir, UploadedCaseConfig(case_id=case_id, generate_candidates=True))
        return result.model_dump()

    async def _run_case_from_uploads(settings: WebApiSettings, config: UploadedCaseConfig, uploads: list[UploadFile]):
        case_dir = prepare_case_dir(settings.web_cases_root, config.case_id)
        await save_uploads(case_dir, uploads)
        result = run_uploaded_case(case_dir, config)
        return result

    @app.get("/api/cases/{case_id}/status")
    def case_status(case_id: str) -> dict[str, Any]:
        return read_status(settings.web_cases_root, case_id)

    @app.get("/api/cases/{case_id}/input-preview")
    def case_input_preview(case_id: str) -> dict[str, Any]:
        path = resolve_under(settings.web_cases_root, validate_case_id(case_id), "input_preview.json")
        if not path.exists():
            raise HTTPException(status_code=404, detail="input preview not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/cases/{case_id}/bundle")
    def case_bundle(case_id: str) -> dict[str, Any]:
        case_id = validate_case_id(case_id)
        product_demo_root = resolve_under(settings.web_cases_root, case_id, "product_demo")
        case_dir = resolve_under(settings.web_cases_root, case_id, "product_demo", case_id)
        if not case_dir.exists():
            raise HTTPException(status_code=404, detail="case bundle not found")
        bundle = load_bundle(product_demo_root, case_id)
        summary = bundle.get("summary", {})
        manifest = bundle.get("manifest", {})
        _attach_boundary(summary)
        _attach_boundary(manifest)
        return {
            "case_id": case_id,
            "summary": summary,
            "tables": bundle.get("tables", {}),
            "figures": _upload_asset_figures(case_id, case_dir, bundle.get("figures", [])),
            "reports": _upload_asset_reports(case_id, bundle.get("reports", [])),
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


def _upload_asset_figures(case_id: str, case_dir: Path, figures_payload: Any) -> list[dict[str, Any]]:
    figures_dir = case_dir / DIRECTORIES["figures"]
    figures: list[dict[str, Any]] = []
    if not isinstance(figures_payload, list):
        return figures
    for details in figures_payload:
        if not isinstance(details, dict):
            continue
        file = str(details.get("file") or "")
        path = figures_dir / file
        asset_path = f"product_demo/{case_id}/{DIRECTORIES['figures']}/{file}"
        figures.append(
            {
                "key": details.get("key") or Path(file).stem,
                "title": details.get("title") or Path(file).stem.replace("_", " ").title(),
                "file": file,
                "url": f"/api/cases/{case_id}/assets/{asset_path}",
                "exists": path.exists() and path.is_file(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
                "source_manifest_available": details.get("source_manifest_available", False),
            }
        )
    return figures


def _upload_asset_reports(case_id: str, reports_payload: Any) -> list[dict[str, Any]]:
    reports = []
    if not isinstance(reports_payload, list):
        return reports
    for report in reports_payload:
        if not isinstance(report, dict):
            continue
        file = str(report.get("file") or report.get("name") or "")
        if not file:
            continue
        asset_path = f"product_demo/{case_id}/{DIRECTORIES['report']}/{file}"
        reports.append(
            {
                "name": report.get("name") or file,
                "file": file,
                "title": report.get("title") or Path(file).stem.replace("_", " ").title(),
                "url": f"/api/cases/{case_id}/assets/{asset_path}",
                "exists": report.get("exists", True),
            }
        )
    return reports


def _attach_boundary(payload: dict[str, Any]) -> None:
    evidence = dict(payload.get("evidence", {}))
    evidence.update(evidence_boundary())
    payload["evidence"] = evidence


app = create_app()
