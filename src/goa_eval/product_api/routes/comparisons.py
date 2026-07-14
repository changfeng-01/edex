from fastapi import APIRouter, Depends

from goa_eval.product.comparison_service import ComparisonClaimError
from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import ProductApiError, translate_domain_error
from goa_eval.product_api.schemas import ComparisonCreate, success


router = APIRouter(prefix="/api/v1")


@router.post("/comparisons")
def create_comparison(
    payload: ComparisonCreate,
    container: ProductContainer = Depends(get_container),
):
    try:
        record = container.comparison_service.compare_versions(
            payload.project_id,
            payload.baseline_design_version_id,
            payload.result_design_version_id,
            payload.baseline_analysis_run_id,
            payload.result_analysis_run_id,
        )
        return success(record, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/comparisons/{comparison_id}")
def get_comparison(comparison_id: str, container: ProductContainer = Depends(get_container)):
    record = container.repository.get_comparison(comparison_id)
    if record is None:
        raise ProductApiError("COMPARISON_NOT_FOUND", "Comparison was not found.", 404)
    return success(record)


@router.post("/candidates/{candidate_id}:confirm")
def confirm_candidate(
    candidate_id: str,
    comparison_id: str,
    container: ProductContainer = Depends(get_container),
):
    try:
        return success(container.comparison_service.confirm_candidate(candidate_id, comparison_id))
    except Exception as exc:
        if isinstance(exc, ComparisonClaimError):
            raise translate_domain_error(exc) from exc
        raise translate_domain_error(exc) from exc
