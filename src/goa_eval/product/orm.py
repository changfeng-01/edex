from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, JSON, String
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
