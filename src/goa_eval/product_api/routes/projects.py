from fastapi import APIRouter, Depends

from goa_eval.product.project_service import ProductNotFoundError
from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import translate_domain_error
from goa_eval.product_api.schemas import DesignVersionCreate, ProjectCreate, success


router = APIRouter(prefix="/api/v1")


@router.post("/projects")
def create_project(payload: ProjectCreate, container: ProductContainer = Depends(get_container)):
    try:
        result = container.project_service.create_project(
            payload.workspace_id,
            payload.name,
            payload.circuit_profile_id,
            payload.spec_revision_id,
        )
        return success(result.project, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/projects/{project_id}")
def get_project(project_id: str, container: ProductContainer = Depends(get_container)):
    project = container.repository.get_project(project_id)
    if project is None:
        raise translate_domain_error(ProductNotFoundError(f"project was not found: {project_id}"))
    return success(project)


@router.get("/projects/{project_id}/overview")
def get_project_overview(project_id: str, container: ProductContainer = Depends(get_container)):
    try:
        return success(container.project_service.get_project_overview(project_id))
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.post("/projects/{project_id}/design-versions")
def create_design_version(
    project_id: str,
    payload: DesignVersionCreate,
    container: ProductContainer = Depends(get_container),
):
    try:
        version = container.project_service.create_design_version(
            project_id,
            payload.label,
            parameter_set_ref=payload.parameter_set_ref,
            netlist_ref=payload.netlist_ref,
            parent_version_id=payload.parent_version_id,
        )
        return success(version, status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/projects/{project_id}/design-versions")
def list_design_versions(project_id: str, container: ProductContainer = Depends(get_container)):
    if container.repository.get_project(project_id) is None:
        raise translate_domain_error(ProductNotFoundError(f"project was not found: {project_id}"))
    return success(container.repository.list_design_versions(project_id))


@router.get("/design-versions/{version_id}")
def get_design_version(version_id: str, container: ProductContainer = Depends(get_container)):
    version = container.repository.get_design_version(version_id)
    if version is None:
        raise translate_domain_error(ProductNotFoundError(f"design version was not found: {version_id}"))
    return success(version)
