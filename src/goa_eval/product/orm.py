from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkspaceORM(Base):
    __tablename__ = "workspaces"

    workspace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(32))


class ProjectORM(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.workspace_id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    circuit_profile_id: Mapped[str] = mapped_column(String(128))
    spec_revision_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(64))


class DesignVersionORM(Base):
    __tablename__ = "design_versions"

    design_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    label: Mapped[str] = mapped_column(String(255))
    parameter_set_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    netlist_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_versions.design_version_id"),
        nullable=True,
    )
    source_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(64))


class AnalysisRunORM(Base):
    __tablename__ = "analysis_runs"

    analysis_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    design_version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.design_version_id"), index=True)
    input_manifest_ref: Mapped[str] = mapped_column(String(1024))
    spec_revision_id: Mapped[str] = mapped_column(String(128))
    profile_revision_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    artifact_bundle_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    evidence_boundary: Mapped[dict[str, Any]] = mapped_column(JSON)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EvidenceRecordORM(Base):
    __tablename__ = "evidence_records"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str] = mapped_column(String(1024))
    checksum: Mapped[str] = mapped_column(String(128))
    boundary: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(64))


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(64))


class OptimizationExperimentORM(Base):
    __tablename__ = "optimization_experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    baseline_design_version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.design_version_id"))
    objective_spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    parameter_space_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    strategy_config: Mapped[dict[str, Any]] = mapped_column(JSON)
    budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    best_confirmed_design_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_versions.design_version_id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(64))


class CandidateORM(Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_experiments.experiment_id"), index=True
    )
    parent_design_version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.design_version_id"))
    parameter_changes: Mapped[dict[str, Any]] = mapped_column(JSON)
    strategy: Mapped[str] = mapped_column(String(128))
    reason_codes: Mapped[list[str]] = mapped_column(JSON)
    selection_scores: Mapped[dict[str, float]] = mapped_column(JSON)
    selection_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    must_resimulate: Mapped[bool] = mapped_column(Boolean)
    simulation_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result_design_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_versions.design_version_id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(64))


class SimulationJobORM(Base):
    __tablename__ = "simulation_jobs"
    __table_args__ = (
        UniqueConstraint("simulation_job_id", "result_sha256", name="uq_simulation_job_result"),
    )

    simulation_job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON)
    adapter_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    input_manifest_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    command_manifest_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_manifest_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logs_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer)
    export_attempt: Mapped[int] = mapped_column(Integer)
    import_attempt: Mapped[int] = mapped_column(Integer)
    batch_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[str] = mapped_column(String(64))


class ComparisonORM(Base):
    __tablename__ = "comparisons"

    comparison_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), index=True)
    baseline_design_version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.design_version_id"))
    result_design_version_id: Mapped[str] = mapped_column(ForeignKey("design_versions.design_version_id"))
    baseline_analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.analysis_run_id"), nullable=True
    )
    result_analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.analysis_run_id"), nullable=True
    )
    metric_deltas: Mapped[dict[str, Any]] = mapped_column(JSON)
    constraint_changes: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    verdict: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(64))
