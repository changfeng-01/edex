from __future__ import annotations

import datetime as dt
from pathlib import Path

from goa_eval.product.analysis_service import AnalysisService
from goa_eval.web.schemas import CaseRunResult, UploadedCaseConfig, evidence_boundary
from goa_eval.web.storage import write_status


def run_uploaded_case(case_dir: Path, config: UploadedCaseConfig) -> CaseRunResult:
    started_at = dt.datetime.now(dt.UTC).isoformat()
    input_dir = case_dir / "input"
    analysis_dir = case_dir / "analysis"
    product_demo_root = case_dir / "product_demo"
    product_demo_case_dir: Path | None = None
    boundary = evidence_boundary()
    write_status(
        case_dir,
        {
            "case_id": config.case_id,
            "status": "running",
            "started_at": started_at,
            "input_dir": _display_path(input_dir),
            "analysis_dir": _display_path(analysis_dir),
            "product_demo_case_dir": None,
            "bundle_url": None,
            "error": None,
            "evidence_boundary": boundary,
        },
    )

    try:
        pipeline_result = AnalysisService(None, None).execute_compatibility(
            input_dir=input_dir,
            analysis_dir=analysis_dir,
            product_demo_root=product_demo_root,
            case_id=config.case_id,
            config=config,
        )
        product_demo_case_dir = pipeline_result.product_demo_case_dir
        result = CaseRunResult(
            case_id=config.case_id,
            status="completed",
            case_dir=_display_path(case_dir),
            input_dir=_display_path(input_dir),
            analysis_dir=_display_path(analysis_dir),
            product_demo_case_dir=_display_path(product_demo_case_dir),
            bundle_url=f"/api/cases/{config.case_id}/bundle",
            error=None,
            evidence_boundary=boundary,
        )
    except Exception as exc:
        result = CaseRunResult(
            case_id=config.case_id,
            status="failed",
            case_dir=_display_path(case_dir),
            input_dir=_display_path(input_dir),
            analysis_dir=_display_path(analysis_dir),
            product_demo_case_dir=_display_path(product_demo_case_dir) if product_demo_case_dir else None,
            bundle_url=None,
            error=str(exc),
            evidence_boundary=boundary,
        )
    finished_at = dt.datetime.now(dt.UTC).isoformat()
    payload = result.model_dump()
    payload["started_at"] = started_at
    payload["finished_at"] = finished_at
    write_status(case_dir, payload)
    return result


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
