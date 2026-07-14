from fastapi import APIRouter, Depends

from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import translate_domain_error
from goa_eval.product_api.schemas import CandidateDecision, CandidateGenerate, ExperimentCreate, success


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
