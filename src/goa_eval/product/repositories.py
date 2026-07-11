from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    AuditEventRecord,
    DesignVersionRecord,
    EvidenceBoundary,
    EvidenceRecord,
    ProjectRecord,
    WorkspaceRecord,
)
from goa_eval.product.orm import (
    AnalysisRunORM,
    AuditEventORM,
    DesignVersionORM,
    EvidenceRecordORM,
    ProjectORM,
    WorkspaceORM,
)


class SqlAlchemyProductRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def add_workspace(self, record: WorkspaceRecord) -> None:
        with self._sessions.begin() as session:
            session.add(WorkspaceORM(**asdict(record)))

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._sessions() as session:
            row = session.get(WorkspaceORM, workspace_id)
            return _workspace_record(row) if row else None

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(WorkspaceORM).order_by(WorkspaceORM.created_at, WorkspaceORM.workspace_id)
            ).all()
            return [_workspace_record(row) for row in rows]

    def add_project(self, record: ProjectRecord) -> None:
        with self._sessions.begin() as session:
            session.add(ProjectORM(**asdict(record)))

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._sessions() as session:
            row = session.get(ProjectORM, project_id)
            return _project_record(row) if row else None

    def list_projects(self, workspace_id: str) -> list[ProjectRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ProjectORM)
                .where(ProjectORM.workspace_id == workspace_id)
                .order_by(ProjectORM.created_at, ProjectORM.project_id)
            ).all()
            return [_project_record(row) for row in rows]

    def add_design_version(self, record: DesignVersionRecord) -> None:
        with self._sessions.begin() as session:
            session.add(DesignVersionORM(**asdict(record)))

    def get_design_version(self, version_id: str) -> DesignVersionRecord | None:
        with self._sessions() as session:
            row = session.get(DesignVersionORM, version_id)
            return _design_version_record(row) if row else None

    def list_design_versions(self, project_id: str) -> list[DesignVersionRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(DesignVersionORM)
                .where(DesignVersionORM.project_id == project_id)
                .order_by(DesignVersionORM.created_at, DesignVersionORM.design_version_id)
            ).all()
            return [_design_version_record(row) for row in rows]

    def add_analysis_run(self, record: AnalysisRunRecord) -> None:
        payload = asdict(record)
        payload["status"] = record.status.value
        with self._sessions.begin() as session:
            session.add(AnalysisRunORM(**payload))

    def update_analysis_run(self, record: AnalysisRunRecord) -> None:
        with self._sessions.begin() as session:
            row = session.get(AnalysisRunORM, record.analysis_run_id)
            if row is None:
                raise KeyError(record.analysis_run_id)
            row.design_version_id = record.design_version_id
            row.input_manifest_ref = record.input_manifest_ref
            row.spec_revision_id = record.spec_revision_id
            row.profile_revision_id = record.profile_revision_id
            row.status = record.status.value
            row.artifact_bundle_ref = record.artifact_bundle_ref
            row.evidence_boundary = asdict(record.evidence_boundary)
            row.started_at = record.started_at
            row.completed_at = record.completed_at

    def get_analysis_run(self, run_id: str) -> AnalysisRunRecord | None:
        with self._sessions() as session:
            row = session.get(AnalysisRunORM, run_id)
            return _analysis_run_record(row) if row else None

    def list_analysis_runs(
        self,
        *,
        project_id: str | None = None,
        design_version_id: str | None = None,
    ) -> list[AnalysisRunRecord]:
        if (project_id is None) == (design_version_id is None):
            raise ValueError("exactly one analysis run scope is required")

        query = select(AnalysisRunORM)
        if project_id is not None:
            query = query.join(
                DesignVersionORM,
                AnalysisRunORM.design_version_id == DesignVersionORM.design_version_id,
            ).where(DesignVersionORM.project_id == project_id)
        else:
            query = query.where(AnalysisRunORM.design_version_id == design_version_id)
        query = query.order_by(AnalysisRunORM.started_at, AnalysisRunORM.analysis_run_id)

        with self._sessions() as session:
            return [_analysis_run_record(row) for row in session.scalars(query).all()]

    def get_latest_analysis_run(self, project_id: str) -> AnalysisRunRecord | None:
        with self._sessions() as session:
            row = session.scalar(
                select(AnalysisRunORM)
                .join(
                    DesignVersionORM,
                    AnalysisRunORM.design_version_id == DesignVersionORM.design_version_id,
                )
                .where(DesignVersionORM.project_id == project_id)
                .order_by(AnalysisRunORM.started_at.desc(), AnalysisRunORM.analysis_run_id.desc())
                .limit(1)
            )
            return _analysis_run_record(row) if row else None

    def add_evidence(self, record: EvidenceRecord) -> None:
        payload = asdict(record)
        payload["boundary"] = asdict(record.boundary)
        with self._sessions.begin() as session:
            session.add(EvidenceRecordORM(**payload))

    def list_evidence(self, subject_type: str, subject_id: str) -> list[EvidenceRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(EvidenceRecordORM)
                .where(EvidenceRecordORM.subject_type == subject_type)
                .where(EvidenceRecordORM.subject_id == subject_id)
                .order_by(EvidenceRecordORM.created_at, EvidenceRecordORM.evidence_id)
            ).all()
            return [_evidence_record(row) for row in rows]

    def append_audit_event(self, record: AuditEventRecord) -> None:
        with self._sessions.begin() as session:
            session.add(AuditEventORM(**asdict(record)))

    def list_audit_events(self, subject_type: str, subject_id: str) -> list[AuditEventRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(AuditEventORM)
                .where(AuditEventORM.subject_type == subject_type)
                .where(AuditEventORM.subject_id == subject_id)
                .order_by(AuditEventORM.created_at, AuditEventORM.event_id)
            ).all()
            return [_audit_event_record(row) for row in rows]


def _project_record(row: ProjectORM) -> ProjectRecord:
    return ProjectRecord(
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        name=row.name,
        circuit_profile_id=row.circuit_profile_id,
        spec_revision_id=row.spec_revision_id,
        status=row.status,
        created_at=row.created_at,
    )


def _workspace_record(row: WorkspaceORM) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace_id=row.workspace_id,
        name=row.name,
        created_at=row.created_at,
        schema_version=row.schema_version,
    )


def _design_version_record(row: DesignVersionORM) -> DesignVersionRecord:
    return DesignVersionRecord(
        design_version_id=row.design_version_id,
        project_id=row.project_id,
        label=row.label,
        parameter_set_ref=row.parameter_set_ref,
        netlist_ref=row.netlist_ref,
        parent_version_id=row.parent_version_id,
        source_candidate_id=row.source_candidate_id,
        created_at=row.created_at,
    )


def _analysis_run_record(row: AnalysisRunORM) -> AnalysisRunRecord:
    return AnalysisRunRecord(
        analysis_run_id=row.analysis_run_id,
        design_version_id=row.design_version_id,
        input_manifest_ref=row.input_manifest_ref,
        spec_revision_id=row.spec_revision_id,
        profile_revision_id=row.profile_revision_id,
        status=AnalysisStatus(row.status),
        artifact_bundle_ref=row.artifact_bundle_ref,
        evidence_boundary=EvidenceBoundary(**row.evidence_boundary),
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _evidence_record(row: EvidenceRecordORM) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row.evidence_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        evidence_type=row.evidence_type,
        source_ref=row.source_ref,
        checksum=row.checksum,
        boundary=EvidenceBoundary(**row.boundary),
        created_at=row.created_at,
    )


def _audit_event_record(row: AuditEventORM) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=row.event_id,
        actor_id=row.actor_id,
        action=row.action,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        details=row.details,
        created_at=row.created_at,
    )
