from fastapi import APIRouter, Depends

from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import translate_domain_error
from goa_eval.product_api.schemas import success


router = APIRouter(prefix="/api/v1")


@router.get("/profiles")
def list_profiles(container: ProductContainer = Depends(get_container)):
    try:
        return success(container.profile_service.list_profiles())
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/profiles:validate")
def validate_profiles(container: ProductContainer = Depends(get_container)):
    return success(container.profile_service.validate())


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str, container: ProductContainer = Depends(get_container)):
    try:
        return success(container.profile_service.get_profile(profile_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc
