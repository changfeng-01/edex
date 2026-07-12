from fastapi import APIRouter, Depends

from goa_eval.product_api.dependencies import ProductContainer, get_container
from goa_eval.product_api.errors import translate_domain_error
from goa_eval.product_api.schemas import WorkspaceCreate, success


router = APIRouter(prefix="/api/v1")


@router.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, container: ProductContainer = Depends(get_container)):
    try:
        return success(container.project_service.create_workspace(payload.name), status_code=201)
    except Exception as exc:
        raise translate_domain_error(exc) from exc


@router.get("/workspaces")
def list_workspaces(container: ProductContainer = Depends(get_container)):
    return success(container.repository.list_workspaces())


@router.get("/workspaces/{workspace_id}/projects")
def list_projects(workspace_id: str, container: ProductContainer = Depends(get_container)):
    if container.repository.get_workspace(workspace_id) is None:
        from goa_eval.product_api.errors import ProductApiError

        raise ProductApiError("WORKSPACE_NOT_FOUND", "Workspace was not found.", 404)
    return success(container.repository.list_projects(workspace_id))
