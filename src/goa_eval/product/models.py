from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from goa_eval.product.artifact_store import ArtifactRef

from goa_eval.product_demo.schemas import default_evidence_boundary


class AnalysisStatus(str, Enum):
    DRAFT = "draft"
    PREVIEWED = "previewed"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"


class InputPreviewStatus(str, Enum):
    READY = "preview_ready"
    READY_WITH_WARNINGS = "preview_ready_with_warnings"
    FAILED = "preview_failed"


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SIMULATION_PENDING = "simulation_pending"
    SIMULATION_FAILED = "simulation_failed"
    RESIMULATED = "resimulated"
    EVALUATED = "evaluated"
    CONFIRMED_IMPROVEMENT = "confirmed_improvement"
    REGRESSED = "regressed"
    NEUTRAL = "neutral"


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    WAITING_FOR_SIMULATION = "waiting_for_simulation"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class SimulationJobStatus(str, Enum):
    DRAFT = "draft"
    EXPORTED = "exported"
    WAITING_FOR_RESULTS = "waiting_for_results"
    VALIDATING = "validating"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComparisonVerdict(str, Enum):
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    NEUTRAL = "neutral"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id(resource: str) -> str:
    prefix = resource.strip().lower()
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError("resource must be a non-empty alphanumeric prefix")
    return f"{prefix}_{uuid.uuid4().hex}"


def _boundary_value(key: str) -> Any:
    return default_evidence_boundary()[key]


@dataclass(frozen=True)
class EvidenceBoundary:
    data_source: str = field(default_factory=lambda: str(_boundary_value("data_source")))
    engineering_validity: str = field(default_factory=lambda: str(_boundary_value("engineering_validity")))
    must_resimulate: bool = field(default_factory=lambda: bool(_boundary_value("must_resimulate")))


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    name: str
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: str = "1.0"


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    workspace_id: str
    name: str
    circuit_profile_id: str
    spec_revision_id: str
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class DesignVersionRecord:
    design_version_id: str
    project_id: str
    label: str
    parameter_set_ref: str | None = None
    netlist_ref: str | None = None
    parent_version_id: str | None = None
    source_candidate_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class AnalysisRunRecord:
    analysis_run_id: str
    design_version_id: str
    input_manifest_ref: str
    spec_revision_id: str
    profile_revision_id: str
    status: AnalysisStatus = AnalysisStatus.DRAFT
    artifact_bundle_ref: str | None = None
    evidence_boundary: EvidenceBoundary = field(default_factory=EvidenceBoundary)
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class AnalysisExecutionResult:
    analysis_run_id: str
    status: AnalysisStatus
    boundary: EvidenceBoundary
    artifact_bundle_ref: ArtifactRef | None = None
    dashboard_bundle_ref: ArtifactRef | None = None
    issue_manifest_ref: ArtifactRef | None = None
    evidence_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    error: dict[str, Any] | None = None


@dataclass(frozen=True)
class IssueRecord:
    issue_id: str
    constraint_key: str
    category: str
    severity: str
    affected_nodes: tuple[str, ...] = ()
    metric_refs: tuple[str, ...] = ()
    possible_causes: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    classification: str = "known"


@dataclass(frozen=True)
class EvidenceIndexSummary:
    run_id: str
    completeness: str
    evidence_ids: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    invalid_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    subject_type: str
    subject_id: str
    evidence_type: str
    source_ref: str
    checksum: str
    boundary: EvidenceBoundary = field(default_factory=EvidenceBoundary)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class AuditEventRecord:
    event_id: str
    actor_id: str
    action: str
    subject_type: str
    subject_id: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ProjectOverview:
    project: ProjectRecord
    design_versions: tuple[DesignVersionRecord, ...]
    version_count: int
    analysis_count: int
    latest_analysis_run: AnalysisRunRecord | None
    latest_analysis_status: AnalysisStatus | None
    evidence_count: int
    evidence_types: tuple[str, ...]


@dataclass(frozen=True)
class OptimizationExperimentRecord:
    experiment_id: str
    project_id: str
    baseline_design_version_id: str
    objective_spec: dict[str, Any] = field(default_factory=dict)
    parameter_space_ref: str | None = None
    strategy_config: dict[str, Any] = field(default_factory=dict)
    budget: int | None = None
    seed: int | None = None
    state: ExperimentStatus = ExperimentStatus.DRAFT
    best_confirmed_design_version_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    experiment_id: str
    parent_design_version_id: str
    parameter_changes: dict[str, Any]
    strategy: str
    reason_codes: tuple[str, ...] = ()
    selection_scores: dict[str, float] = field(default_factory=dict)
    selection_score: float | None = None
    evaluated_score: float | None = None
    status: CandidateStatus = CandidateStatus.PROPOSED
    must_resimulate: bool = True
    simulation_job_id: str | None = None
    result_design_version_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class SimulationJobRecord:
    simulation_job_id: str
    project_id: str
    candidate_ids: tuple[str, ...]
    adapter_type: str
    status: SimulationJobStatus = SimulationJobStatus.DRAFT
    input_manifest_ref: str | None = None
    command_manifest_ref: str | None = None
    result_manifest_ref: str | None = None
    logs_ref: str | None = None
    attempt: int = 0
    export_attempt: int = 0
    import_attempt: int = 0
    batch_ref: ArtifactRef | None = None
    result_ref: ArtifactRef | None = None
    result_sha256: str | None = None
    error_code: str | None = None
    retryable: bool = False
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ComparisonRecord:
    comparison_id: str
    project_id: str
    baseline_design_version_id: str
    result_design_version_id: str
    baseline_analysis_run_id: str | None
    result_analysis_run_id: str | None
    metric_deltas: dict[str, Any] = field(default_factory=dict)
    constraint_changes: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    verdict: ComparisonVerdict = ComparisonVerdict.EVIDENCE_INSUFFICIENT
    created_at: str = field(default_factory=utc_now_iso)
