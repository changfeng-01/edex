from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str


class ProjectCreate(BaseModel):
    workspace_id: str
    name: str
    circuit_profile_id: str
    spec_revision_id: str


class DesignVersionCreate(BaseModel):
    label: str
    parameter_set_ref: str | None = None
    netlist_ref: str | None = None
    parent_version_id: str | None = None


class ArtifactRefDto(BaseModel):
    uri: str
    key: str
    size_bytes: int = Field(ge=0)
    sha256: str


class AnalysisRunCreate(BaseModel):
    input_manifest_ref: ArtifactRefDto
    case_id: str
    circuit_profile: str | None = None
    topology: str | None = None
    stage_count: int | None = Field(default=None, ge=1)
    output_node_pattern: str = "o{index}"
    generate_readonly_suggestions: bool = True
    run_llm_analysis: bool = False


def success(data: Any, *, status_code: int = 200):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={"schema_version": "1.0", "data": jsonable_encoder(data)},
    )
