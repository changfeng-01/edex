from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.web_api.config import DashboardApiSettings
from goa_eval.web_api.loaders import (
    list_cases,
    load_bundle,
    load_figures,
    load_manifest,
    load_reports,
    load_summary,
    load_tables,
)
from goa_eval.web_api.schemas import BuildDemoRequest
from goa_eval.web_api.security import (
    ALLOWED_FIGURE_EXTENSIONS,
    ALLOWED_REPORT_EXTENSIONS,
    resolve_case_dir,
    resolve_under,
    validate_case_id,
    validate_filename,
    validate_repo_relative_path,
)


def create_app(settings: DashboardApiSettings | None = None) -> FastAPI:
    settings = settings or DashboardApiSettings.from_env()
    app = FastAPI(title="CircuitPilot Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "circuitpilot-dashboard-api"}

    @app.get("/api/cases")
    def cases() -> dict[str, object]:
        return list_cases(settings.product_demo_root)

    @app.get("/api/cases/{case_id}/summary")
    def case_summary(case_id: str) -> dict[str, object]:
        return load_summary(settings.product_demo_root, case_id)

    @app.get("/api/cases/{case_id}/tables")
    def case_tables(case_id: str) -> dict[str, object]:
        return load_tables(settings.product_demo_root, case_id)

    @app.get("/api/cases/{case_id}/figures")
    def case_figures(case_id: str) -> dict[str, object]:
        return load_figures(settings.product_demo_root, case_id)

    @app.get("/api/cases/{case_id}/figures/{filename}")
    def figure_file(case_id: str, filename: str) -> FileResponse:
        filename = validate_filename(filename, ALLOWED_FIGURE_EXTENSIONS)
        case_dir = resolve_case_dir(settings.product_demo_root, case_id)
        path = resolve_under(case_dir / "05_figures", filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="figure not found")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.get("/api/cases/{case_id}/reports")
    def case_reports(case_id: str) -> dict[str, object]:
        return load_reports(settings.product_demo_root, case_id)

    @app.get("/api/cases/{case_id}/reports/{filename}")
    def report_file(case_id: str, filename: str) -> Response:
        filename = validate_filename(filename, ALLOWED_REPORT_EXTENSIONS)
        case_dir = resolve_case_dir(settings.product_demo_root, case_id)
        path = resolve_under(case_dir / "07_report", filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="report not found")
        return Response(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")

    @app.get("/api/cases/{case_id}/bundle")
    def case_bundle(case_id: str) -> dict[str, object]:
        return load_bundle(settings.product_demo_root, case_id)

    @app.get("/api/cases/{case_id}/manifest")
    def case_manifest(case_id: str) -> dict[str, object]:
        return load_manifest(settings.product_demo_root, case_id)

    @app.post("/api/cases/{case_id}/build-demo")
    def build_demo(case_id: str, request: BuildDemoRequest) -> dict[str, str]:
        if not settings.enable_build_api:
            raise HTTPException(status_code=403, detail="build API disabled")
        case_id = validate_case_id(case_id)
        repo_root = Path.cwd()
        input_dir = validate_repo_relative_path(request.input_dir, repo_root)
        output_dir = validate_repo_relative_path(request.output_dir, repo_root)
        case_dir = run_product_demo(input_dir=input_dir, output_dir=output_dir, case_id=case_id)
        return {"case_id": case_id, "case_dir": str(case_dir)}

    return app


app = create_app()
