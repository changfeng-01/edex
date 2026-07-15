from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import sessionmaker

from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    AuditEventRecord,
    CandidateRecord,
    CandidateStatus,
    ComparisonRecord,
    ComparisonVerdict,
    DesignVersionRecord,
    EvidenceBoundary,
    EvidenceRecord,
    ExperimentStatus,
    OptimizationExperimentRecord,
    ProjectRecord,
    SimulationJobRecord,
    SimulationJobStatus,
    WorkspaceRecord,
)
from goa_eval.product.orm import (
    AnalysisRunORM,
    AuditEventORM,
    CandidateORM,
    ComparisonORM,
    DesignVersionORM,
    EvidenceRecordORM,
    OptimizationExperimentORM,
    ProjectORM,
    SimulationJobORM,
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

    def add_experiment(self, record: OptimizationExperimentRecord) -> None:
        payload = asdict(record)
        payload["state"] = record.state.value
        with self._sessions.begin() as session:
            session.add(OptimizationExperimentORM(**payload))

    def update_experiment(self, record: OptimizationExperimentRecord) -> None:
        with self._sessions.begin() as session:
            row = session.get(OptimizationExperimentORM, record.experiment_id)
            if row is None:
                raise KeyError(record.experiment_id)
            _assign_experiment(row, record)

    def get_experiment(self, experiment_id: str) -> OptimizationExperimentRecord | None:
        with self._sessions() as session:
            row = session.get(OptimizationExperimentORM, experiment_id)
            return _experiment_record(row) if row else None

    def add_candidate(self, record: CandidateRecord) -> None:
        payload = asdict(record)
        payload["reason_codes"] = list(record.reason_codes)
        payload["status"] = record.status.value
        with self._sessions.begin() as session:
            session.add(CandidateORM(**payload))

    def update_candidate(self, record: CandidateRecord) -> None:
        with self._sessions.begin() as session:
            row = session.get(CandidateORM, record.candidate_id)
            if row is None:
                raise KeyError(record.candidate_id)
            _assign_candidate(row, record)

    def get_candidate(self, candidate_id: str) -> CandidateRecord | None:
        with self._sessions() as session:
            row = session.get(CandidateORM, candidate_id)
            return _candidate_record(row) if row else None

    def list_candidates(self, experiment_id: str) -> list[CandidateRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(CandidateORM)
                .where(CandidateORM.experiment_id == experiment_id)
                .order_by(CandidateORM.created_at, CandidateORM.candidate_id)
            ).all()
            return [_candidate_record(row) for row in rows]

    def add_simulation_job(self, record: SimulationJobRecord) -> None:
        payload = asdict(record)
        payload["candidate_ids"] = list(record.candidate_ids)
        payload["status"] = record.status.value
        with self._sessions.begin() as session:
            session.add(SimulationJobORM(**payload))

    def update_simulation_job(self, record: SimulationJobRecord) -> None:
        with self._sessions.begin() as session:
            row = session.get(SimulationJobORM, record.simulation_job_id)
            if row is None:
                raise KeyError(record.simulation_job_id)
            _assign_simulation_job(row, record)

    def get_simulation_job(self, job_id: str) -> SimulationJobRecord | None:
        with self._sessions() as session:
            row = session.get(SimulationJobORM, job_id)
            return _simulation_job_record(row) if row else None

    def claim_simulation_job(self, job_id: str) -> SimulationJobRecord | None:
        """Atomically move one queued job to running and increment its attempt."""
        with self._sessions.begin() as session:
            result = session.execute(
                update(SimulationJobORM)
                .where(SimulationJobORM.simulation_job_id == job_id)
                .where(SimulationJobORM.status == SimulationJobStatus.QUEUED.value)
                .values(
                    status=SimulationJobStatus.RUNNING.value,
                    attempt=SimulationJobORM.attempt + 1,
                    error_code=None,
                    retryable=False,
                )
            )
            if result.rowcount != 1:
                return None
        return self.get_simulation_job(job_id)

    def list_simulation_jobs(self, project_id: str) -> list[SimulationJobRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(SimulationJobORM)
                .where(SimulationJobORM.project_id == project_id)
                .order_by(SimulationJobORM.created_at, SimulationJobORM.simulation_job_id)
            ).all()
            return [_simulation_job_record(row) for row in rows]

    def add_comparison(self, record: ComparisonRecord) -> None:
        payload = asdict(record)
        payload["evidence_ids"] = list(record.evidence_ids)
        payload["verdict"] = record.verdict.value
        with self._sessions.begin() as session:
            session.add(ComparisonORM(**payload))

    def get_comparison(self, comparison_id: str) -> ComparisonRecord | None:
        with self._sessions() as session:
            row = session.get(ComparisonORM, comparison_id)
            return _comparison_record(row) if row else None

    def list_comparisons(self, project_id: str) -> list[ComparisonRecord]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ComparisonORM)
                .where(ComparisonORM.project_id == project_id)
                .order_by(ComparisonORM.created_at, ComparisonORM.comparison_id)
            ).all()
            return [_comparison_record(row) for row in rows]


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


def _experiment_record(row: OptimizationExperimentORM) -> OptimizationExperimentRecord:
    return OptimizationExperimentRecord(
        experiment_id=row.experiment_id,
        project_id=row.project_id,
        baseline_design_version_id=row.baseline_design_version_id,
        objective_spec=row.objective_spec,
        parameter_space_ref=row.parameter_space_ref,
        strategy_config=row.strategy_config,
        budget=row.budget,
        seed=row.seed,
        state=ExperimentStatus(row.state),
        best_confirmed_design_version_id=row.best_confirmed_design_version_id,
        created_at=row.created_at,
    )


def _candidate_record(row: CandidateORM) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=row.candidate_id,
        experiment_id=row.experiment_id,
        parent_design_version_id=row.parent_design_version_id,
        parameter_changes=row.parameter_changes,
        strategy=row.strategy,
        reason_codes=tuple(row.reason_codes),
        selection_scores=row.selection_scores,
        selection_score=row.selection_score,
        evaluated_score=row.evaluated_score,
        status=CandidateStatus(row.status),
        must_resimulate=row.must_resimulate,
        simulation_job_id=row.simulation_job_id,
        result_design_version_id=row.result_design_version_id,
        created_at=row.created_at,
    )


def _artifact_ref(payload: dict | None):
    from goa_eval.product.artifact_store import ArtifactRef

    return ArtifactRef(**payload) if payload else None


def _simulation_job_record(row: SimulationJobORM) -> SimulationJobRecord:
    return SimulationJobRecord(
        simulation_job_id=row.simulation_job_id,
        project_id=row.project_id,
        candidate_ids=tuple(row.candidate_ids),
        adapter_type=row.adapter_type,
        status=SimulationJobStatus(row.status),
        input_manifest_ref=row.input_manifest_ref,
        command_manifest_ref=row.command_manifest_ref,
        result_manifest_ref=row.result_manifest_ref,
        logs_ref=row.logs_ref,
        attempt=row.attempt,
        export_attempt=row.export_attempt,
        import_attempt=row.import_attempt,
        batch_ref=_artifact_ref(row.batch_ref),
        result_ref=_artifact_ref(row.result_ref),
        result_sha256=row.result_sha256,
        error_code=row.error_code,
        retryable=row.retryable,
        created_at=row.created_at,
    )


def _comparison_record(row: ComparisonORM) -> ComparisonRecord:
    return ComparisonRecord(
        comparison_id=row.comparison_id,
        project_id=row.project_id,
        baseline_design_version_id=row.baseline_design_version_id,
        result_design_version_id=row.result_design_version_id,
        baseline_analysis_run_id=row.baseline_analysis_run_id,
        result_analysis_run_id=row.result_analysis_run_id,
        metric_deltas=row.metric_deltas,
        constraint_changes=row.constraint_changes,
        evidence_ids=tuple(row.evidence_ids),
        verdict=ComparisonVerdict(row.verdict),
        created_at=row.created_at,
    )


def _assign_experiment(row: OptimizationExperimentORM, record: OptimizationExperimentRecord) -> None:
    row.objective_spec = record.objective_spec
    row.parameter_space_ref = record.parameter_space_ref
    row.strategy_config = record.strategy_config
    row.budget = record.budget
    row.seed = record.seed
    row.state = record.state.value
    row.best_confirmed_design_version_id = record.best_confirmed_design_version_id


def _assign_candidate(row: CandidateORM, record: CandidateRecord) -> None:
    row.parameter_changes = record.parameter_changes
    row.strategy = record.strategy
    row.reason_codes = list(record.reason_codes)
    row.selection_scores = record.selection_scores
    row.selection_score = record.selection_score
    row.evaluated_score = record.evaluated_score
    row.status = record.status.value
    row.must_resimulate = record.must_resimulate
    row.simulation_job_id = record.simulation_job_id
    row.result_design_version_id = record.result_design_version_id


def _assign_simulation_job(row: SimulationJobORM, record: SimulationJobRecord) -> None:
    row.candidate_ids = list(record.candidate_ids)
    row.adapter_type = record.adapter_type
    row.status = record.status.value
    row.input_manifest_ref = record.input_manifest_ref
    row.command_manifest_ref = record.command_manifest_ref
    row.result_manifest_ref = record.result_manifest_ref
    row.logs_ref = record.logs_ref
    row.attempt = record.attempt
    row.export_attempt = record.export_attempt
    row.import_attempt = record.import_attempt
    row.batch_ref = asdict(record.batch_ref) if record.batch_ref else None
    row.result_ref = asdict(record.result_ref) if record.result_ref else None
    row.result_sha256 = record.result_sha256
    row.error_code = record.error_code
    row.retryable = record.retryable
