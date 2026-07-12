from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends

from goa_eval.product.artifact_store import ArtifactRef
from goa_eval.product.models import AnalysisStatus
from goa_eval.product.project_service import ProductNotFoundError
from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import ProductApiError, translate_domain_error
from goa_eval.product_api.schemas import AnalysisRunCreate, success
from goa_eval.web.schemas import UploadedCaseConfig


router = APIRouter(prefix="/api/v1")


@router.post("/design-versions/{version_id}/analysis-runs")
def create_analysis_run(
    version_id: str,
    payload: AnalysisRunCreate,
    container: ProductContainer = Depends(get_container),
):
    if container.repository.get_design_version(version_id) is None:
        raise translate_domain_error(ProductNotFoundError(f"design version was not found: {version_id}"))
    active = container.repository.list_analysis_runs(design_version_id=version_id)
    if any(run.status in {AnalysisStatus.QUEUED, AnalysisStatus.RUNNING} for run in active):
        raise ProductApiError("ANALYSIS_STATE_CONFLICT", "Analysis state does not allow this operation.", 409)
    ref = ArtifactRef(**payload.input_manifest_ref.model_dump())
    config = UploadedCaseConfig(
        case_id=payload.case_id,
        circuit_profile=payload.circuit_profile,
        topology=payload.topology,
        stage_count=payload.stage_count,
        output_node_pattern=payload.output_node_pattern,
        generate_candidates=payload.generate_readonly_suggestions,
        run_llm_analysis=payload.run_llm_analysis,
    )
    try:
        result = container.analysis_service.run_analysis(
            design_version_id=version_id,
            input_manifest_ref=ref,
            config=config,
        )
    except Exception as exc:
        raise ProductApiError("ANALYSIS_EXECUTION_FAILED", "Analysis execution failed.", 500) from exc
    if result.status == AnalysisStatus.FAILED:
        raise ProductApiError("ANALYSIS_EXECUTION_FAILED", "Analysis execution failed.", 500)
    return success(result, status_code=201)


@router.get("/analysis-runs/{run_id}")
def get_analysis_run(run_id: str, container: ProductContainer = Depends(get_container)):
    return success(_require_run(container, run_id))


@router.get("/analysis-runs/{run_id}/bundle")
def get_analysis_bundle(run_id: str, container: ProductContainer = Depends(get_container)):
    run = _require_run(container, run_id)
    evidence = container.repository.list_evidence("analysis_run", run_id)
    return success(
        {
            "analysis_run_id": run_id,
            "artifact_bundle_ref": run.artifact_bundle_ref,
            "artifacts": [record.source_ref for record in evidence],
        }
    )


@router.get("/analysis-runs/{run_id}/issues")
def get_analysis_issues(run_id: str, container: ProductContainer = Depends(get_container)):
    _require_run(container, run_id)
    records = container.repository.list_evidence("analysis_run", run_id)
    issue = next((record for record in records if record.source_ref.endswith("/issues.json")), None)
    if issue is None:
        raise ProductApiError("ARTIFACT_NOT_FOUND", "Artifact was not found.", 404)
    try:
        ref = container.ref_from_uri(issue.source_ref, issue.checksum)
        return success(json.loads(container.artifact_store.resolve(ref).read_text(encoding="utf-8")))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/analysis-runs/{run_id}/evidence")
def get_analysis_evidence(run_id: str, container: ProductContainer = Depends(get_container)):
    run = _require_run(container, run_id)
    records = container.repository.list_evidence("analysis_run", run_id)
    return success({"boundary": asdict(run.evidence_boundary), "records": records})


def _require_run(container: ProductContainer, run_id: str):
    run = container.repository.get_analysis_run(run_id)
    if run is None:
        raise ProductApiError("ANALYSIS_RUN_NOT_FOUND", "Analysis run was not found.", 404)
    return run
