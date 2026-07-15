from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from goa_eval.product.artifact_store import ArtifactStoreError
from goa_eval.product.input_service import InputPreviewFailed
from goa_eval.product.comparison_service import ComparisonClaimError
from goa_eval.product.experiment_service import ExperimentConflict, ExperimentNotFound
from goa_eval.product.job_runner import JobExecutionDisabled
from goa_eval.product.project_service import InvalidCircuitProfile, ProductNotFoundError
from goa_eval.product.simulation_job_service import SimulationImportError, SimulationJobConflict
from goa_eval.product.state_machine import InvalidTransition


@dataclass
class ProductApiError(Exception):
    error_code: str
    message: str
    status_code: int
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    artifact_refs: list[str] = field(default_factory=list)


def error_response(error: ProductApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error_code": error.error_code,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
            "artifact_refs": error.artifact_refs,
        },
    )


async def product_error_handler(_request: Request, exc: ProductApiError) -> JSONResponse:
    return error_response(exc)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        ProductApiError(
            "INPUT_PREVIEW_FAILED",
            "Request validation failed.",
            422,
            details={"errors": exc.errors()},
        )
    )


async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        ProductApiError(
            "ANALYSIS_EXECUTION_FAILED",
            "Analysis execution failed.",
            500,
        )
    )


def translate_domain_error(exc: Exception) -> ProductApiError:
    if isinstance(exc, ProductApiError):
        return exc
    if isinstance(exc, InvalidCircuitProfile):
        return ProductApiError("CIRCUIT_PROFILE_INVALID", "Circuit profile is invalid.", 422)
    if isinstance(exc, InputPreviewFailed):
        return ProductApiError(
            "INPUT_PREVIEW_FAILED",
            "Input preview failed.",
            422,
            details={"preview": exc.preview},
        )
    if isinstance(exc, ProductNotFoundError):
        text = str(exc).lower()
        if "workspace" in text:
            return ProductApiError("WORKSPACE_NOT_FOUND", "Workspace was not found.", 404)
        if "design version" in text:
            return ProductApiError("DESIGN_VERSION_NOT_FOUND", "Design version was not found.", 404)
        if "project" in text:
            return ProductApiError("PROJECT_NOT_FOUND", "Project was not found.", 404)
        return ProductApiError("ARTIFACT_NOT_FOUND", "Artifact was not found.", 404)
    if isinstance(exc, ExperimentNotFound):
        return ProductApiError("EXPERIMENT_NOT_FOUND", "Experiment or candidate was not found.", 404)
    if isinstance(exc, SimulationJobConflict):
        if "not found" in str(exc).lower():
            return ProductApiError("SIMULATION_JOB_NOT_FOUND", "Simulation job was not found.", 404)
        return ProductApiError("EXPERIMENT_STATE_CONFLICT", "Experiment state does not allow this operation.", 409)
    if isinstance(exc, JobExecutionDisabled):
        return ProductApiError("JOB_EXECUTION_DISABLED", "Simulation job execution is disabled.", 409)
    if isinstance(exc, (ExperimentConflict, InvalidTransition)):
        return ProductApiError("EXPERIMENT_STATE_CONFLICT", "Experiment state does not allow this operation.", 409)
    if isinstance(exc, SimulationImportError):
        return ProductApiError("RESULT_CONTRACT_INVALID", "Simulation result contract is invalid.", 422, retryable=True)
    if isinstance(exc, ComparisonClaimError):
        return ProductApiError("EVIDENCE_INSUFFICIENT", "Evaluated evidence is insufficient.", 409)
    if isinstance(exc, (ArtifactStoreError, FileNotFoundError)):
        return ProductApiError("ARTIFACT_NOT_FOUND", "Artifact was not found.", 404)
    if isinstance(exc, ValueError):
        return ProductApiError("INPUT_PREVIEW_FAILED", "Input preview failed.", 422)
    return ProductApiError("ANALYSIS_EXECUTION_FAILED", "Analysis execution failed.", 500)
