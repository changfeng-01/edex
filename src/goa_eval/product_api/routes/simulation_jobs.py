from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Depends, File, UploadFile

from goa_eval.product.simulation_job_service import SimulationJobConflict
from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import ProductApiError, translate_domain_error
from goa_eval.product_api.schemas import ImportCommit, SimulationJobCreate, success


router = APIRouter(prefix="/api/v1")
MAX_RESULT_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/simulation-jobs")
def create_simulation_job(
    payload: SimulationJobCreate,
    container: ProductContainer = Depends(get_container),
):
    try:
        if payload.adapter_type == "manual":
            record = container.simulation_job_service.create_manual_job(payload.candidate_ids)
        else:
            availability = container.simulator_registry.availability(payload.adapter_type)
            if availability.execution_enabled:
                record = container.simulation_job_service.create_execution_job(
                    payload.candidate_ids,
                    payload.adapter_type,
                    payload.input_manifest_ref,
                )
            else:
                record = container.simulation_job_service.create_offline_job(
                    payload.candidate_ids,
                    payload.adapter_type,
                )
        return success(record, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/simulation-jobs/{job_id}")
def get_simulation_job(job_id: str, container: ProductContainer = Depends(get_container)):
    record = container.repository.get_simulation_job(job_id)
    if record is None:
        raise translate_domain_error(SimulationJobConflict(f"simulation job was not found: {job_id}"))
    return success(record)


@router.post("/simulation-jobs/{job_id}:export")
def export_simulation_job(job_id: str, container: ProductContainer = Depends(get_container)):
    try:
        return success(container.simulation_job_service.export_job(job_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/simulation-jobs/{job_id}/imports:preview")
async def preview_import(
    job_id: str,
    results: UploadFile = File(...),
    container: ProductContainer = Depends(get_container),
):
    data = await results.read(MAX_RESULT_UPLOAD_BYTES + 1)
    if len(data) > MAX_RESULT_UPLOAD_BYTES:
        raise ProductApiError("RESULT_UPLOAD_TOO_LARGE", "Simulation result upload is too large.", 413)
    try:
        with TemporaryDirectory(prefix="circuitpilot-result-import-") as temporary:
            path = Path(temporary) / "results.csv"
            path.write_bytes(data)
            return success(container.simulation_job_service.preview_import(job_id, path))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/simulation-jobs/{job_id}/imports:commit")
def commit_import(
    job_id: str,
    payload: ImportCommit,
    container: ProductContainer = Depends(get_container),
):
    try:
        return success(container.simulation_job_service.commit_import(job_id, payload.manifest_sha256))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/simulation-jobs/{job_id}:retry")
def retry_job(job_id: str, container: ProductContainer = Depends(get_container)):
    try:
        job = container.repository.get_simulation_job(job_id)
        if job is None:
            raise SimulationJobConflict(f"simulation job was not found: {job_id}")
        retried = (
            container.simulation_job_service.retry_job(job_id)
            if job.adapter_type == "manual"
            else container.simulation_job_service.retry_execution(job_id)
        )
        return success(retried)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/simulation-jobs/{job_id}:queue")
def queue_job(job_id: str, container: ProductContainer = Depends(get_container)):
    try:
        return success(container.simulation_job_service.queue_execution(job_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/simulation-jobs/{job_id}:execute")
def execute_job(job_id: str, container: ProductContainer = Depends(get_container)):
    try:
        result = container.job_runner.run_job(job_id)
        if result is None:
            raise SimulationJobConflict("simulation job is not available for execution")
        return success(container.simulation_job_service.commit_execution_outputs(job_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc
