from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EvidenceBoundary(FlexibleModel):
    data_source: str | None = None
    engineering_validity: str | None = None
    evidence_level: str | None = None
    simulation_backend: str | None = None
    mock_used: bool | str | None = None
    pdk_available: bool | str | None = None
    ngspice_available: bool | str | None = None
    reportable_as_real_ngspice: bool | str | None = None
    optimizer_claim_level: str | None = None


class DashboardSummary(FlexibleModel):
    case_id: str
    run_id: str | None = None
    overall_status: str | None = None
    overall_score: float | str | None = None
    hard_constraint_passed: bool | str | None = None
    validation_status: str | None = None
    candidate_status: str | None = None
    evidence: EvidenceBoundary | dict[str, Any] = Field(default_factory=dict)


class ErrorState(FlexibleModel):
    missing: bool = True
    message: str


class CaseInfo(FlexibleModel):
    case_id: str
    path: str
    has_manifest: bool
    has_summary: bool
    validation_status: str = "unknown"
    candidate_status: str = "unknown"


class TablePayload(FlexibleModel):
    file: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    missing: bool = False
    message: str | None = None


class DashboardTables(FlexibleModel):
    run_summary: TablePayload
    constraints: TablePayload
    candidates: TablePayload
    before_after: TablePayload


class FigureInfo(FlexibleModel):
    key: str
    title: str
    file: str
    url: str
    exists: bool
    size_bytes: int = 0


class ReportInfo(FlexibleModel):
    name: str
    url: str
    exists: bool


class DashboardBundle(FlexibleModel):
    case_id: str
    summary: dict[str, Any]
    tables: dict[str, Any]
    figures: list[dict[str, Any]]
    reports: list[dict[str, Any]]
    manifest: dict[str, Any]


class BuildDemoRequest(BaseModel):
    input_dir: str = "examples/demo_run"
    output_dir: str = "outputs/product_demo"
