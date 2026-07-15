import shutil
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory

from fastapi import APIRouter, Depends

from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import translate_domain_error
from goa_eval.product_api.schemas import CandidateDecision, CandidateGenerate, ExperimentCreate, PiaOutputMap, success


router = APIRouter(prefix="/api/v1")


@router.post("/projects/{project_id}/experiments")
def create_experiment(
    project_id: str,
    payload: ExperimentCreate,
    container: ProductContainer = Depends(get_container),
):
    try:
        record = container.experiment_service.create_experiment(
            project_id,
            payload.baseline_design_version_id,
            payload.strategy_config,
        )
        return success(record, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, container: ProductContainer = Depends(get_container)):
    record = container.repository.get_experiment(experiment_id)
    if record is None:
        from goa_eval.product.experiment_service import ExperimentNotFound

        raise translate_domain_error(ExperimentNotFound(experiment_id))
    return success(record)


@router.get("/experiments/{experiment_id}/candidates")
def list_candidates(experiment_id: str, container: ProductContainer = Depends(get_container)):
    if container.repository.get_experiment(experiment_id) is None:
        from goa_eval.product.experiment_service import ExperimentNotFound

        raise translate_domain_error(ExperimentNotFound(experiment_id))
    return success(container.repository.list_candidates(experiment_id))


@router.post("/experiments/{experiment_id}/candidates:generate")
def generate_candidates(
    experiment_id: str,
    payload: CandidateGenerate,
    container: ProductContainer = Depends(get_container),
):
    try:
        records = container.experiment_service.generate_candidates(
            experiment_id,
            payload.strategy,
            payload.max_candidates,
            payload.seed,
        )
        return success(records, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/experiments/{experiment_id}/pia-output:map")
def map_pia_output(
    experiment_id: str,
    payload: PiaOutputMap,
    container: ProductContainer = Depends(get_container),
):
    try:
        with TemporaryDirectory(prefix="circuitpilot-pia-map-") as temporary_name:
            from pathlib import Path

            output = Path(temporary_name).resolve()
            seen: set[str] = set()
            for artifact in payload.artifacts:
                relative = PurePosixPath(artifact.relative_path)
                normalized = relative.as_posix()
                if (
                    relative.is_absolute()
                    or "\\" in artifact.relative_path
                    or any(part in {"", ".", ".."} for part in relative.parts)
                    or normalized in seen
                ):
                    raise ValueError(f"invalid or duplicate PIA artifact path: {artifact.relative_path}")
                ref = container.artifact_store.ref_from_uri(
                    artifact.artifact_ref.uri,
                    artifact.artifact_ref.sha256,
                )
                destination = output.joinpath(*relative.parts).resolve()
                if output not in destination.parents:
                    raise ValueError(f"PIA artifact path escapes the mapping workspace: {artifact.relative_path}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(container.artifact_store.resolve(ref), destination)
                seen.add(normalized)
            mapping = container.pia_adapter.map_output(
                experiment_id,
                output,
                parameter_columns=tuple(payload.parameter_columns),
            )
        return success(mapping)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/candidates/{candidate_id}:approve")
def approve_candidate(
    candidate_id: str,
    payload: CandidateDecision,
    container: ProductContainer = Depends(get_container),
):
    try:
        return success(container.experiment_service.approve_candidate(candidate_id, payload.actor_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/candidates/{candidate_id}:reject")
def reject_candidate(
    candidate_id: str,
    payload: CandidateDecision,
    container: ProductContainer = Depends(get_container),
):
    try:
        return success(
            container.experiment_service.reject_candidate(
                candidate_id,
                payload.actor_id,
                payload.reason or "rejected",
            )
        )
    except Exception as exc:
        raise translate_domain_error(exc) from exc
