from dataclasses import replace

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from goa_eval.product.artifact_store import ArtifactRef
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import (
    CandidateRecord,
    ComparisonRecord,
    ComparisonVerdict,
    OptimizationExperimentRecord,
    ProjectRecord,
    SimulationJobRecord,
    SimulationJobStatus,
    WorkspaceRecord,
    DesignVersionRecord,
    new_id,
)
from goa_eval.product.repositories import SqlAlchemyProductRepository


def build_repository(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'phase2.db'}")
    create_schema(engine)
    return engine, SqlAlchemyProductRepository(engine)


def seed_project(repo):
    workspace = WorkspaceRecord(workspace_id=new_id("workspace"), name="GOA team")
    project = ProjectRecord(
        project_id=new_id("project"),
        workspace_id=workspace.workspace_id,
        name="720-stage GOA",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )
    baseline = DesignVersionRecord(
        design_version_id=new_id("version"),
        project_id=project.project_id,
        label="baseline",
    )
    result = DesignVersionRecord(
        design_version_id=new_id("version"),
        project_id=project.project_id,
        label="candidate result",
        parent_version_id=baseline.design_version_id,
    )
    repo.add_workspace(workspace)
    repo.add_project(project)
    repo.add_design_version(baseline)
    repo.add_design_version(result)
    return project, baseline, result


def artifact_ref(key: str, payload: bytes = b"phase2") -> ArtifactRef:
    import hashlib

    return ArtifactRef(
        uri=f"artifact://{key}",
        key=key,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_phase2_records_round_trip_without_artifact_bytes(tmp_path):
    _, repo = build_repository(tmp_path)
    project, baseline, result = seed_project(repo)
    experiment = OptimizationExperimentRecord(
        experiment_id=new_id("experiment"),
        project_id=project.project_id,
        baseline_design_version_id=baseline.design_version_id,
        strategy_config={"strategy": "rule", "weights": {"ripple": 0.7}},
        seed=17,
    )
    candidate = CandidateRecord(
        candidate_id=new_id("candidate"),
        experiment_id=experiment.experiment_id,
        parent_design_version_id=baseline.design_version_id,
        parameter_changes={"t1_width_um": 12.5},
        strategy="rule",
        reason_codes=("reduce_ripple",),
        selection_score=0.82,
        evaluated_score=None,
    )
    batch_ref = artifact_ref("phase2/jobs/job_1/batch.csv", b"candidate_id\n")
    job = SimulationJobRecord(
        simulation_job_id=new_id("job"),
        project_id=project.project_id,
        candidate_ids=(candidate.candidate_id,),
        adapter_type="manual",
        status=SimulationJobStatus.EXPORTED,
        export_attempt=1,
        import_attempt=0,
        batch_ref=batch_ref,
    )
    comparison = ComparisonRecord(
        comparison_id=new_id("comparison"),
        project_id=project.project_id,
        baseline_design_version_id=baseline.design_version_id,
        result_design_version_id=result.design_version_id,
        baseline_analysis_run_id=None,
        result_analysis_run_id=None,
        metric_deltas={"overall_score": 0.1},
        constraint_changes={"ripple": "pass"},
        evidence_ids=("evidence_baseline", "evidence_result"),
        verdict=ComparisonVerdict.EVIDENCE_INSUFFICIENT,
    )

    repo.add_experiment(experiment)
    repo.add_candidate(candidate)
    repo.add_simulation_job(job)
    repo.add_comparison(comparison)

    assert repo.get_experiment(experiment.experiment_id) == experiment
    assert repo.list_candidates(experiment.experiment_id) == [candidate]
    assert repo.get_simulation_job(job.simulation_job_id) == job
    assert repo.list_simulation_jobs(project.project_id) == [job]
    assert repo.get_comparison(comparison.comparison_id) == comparison
    assert repo.list_comparisons(project.project_id) == [comparison]
    assert repo.get_simulation_job(job.simulation_job_id).batch_ref == batch_ref


def test_phase2_records_can_be_updated(tmp_path):
    _, repo = build_repository(tmp_path)
    project, baseline, _ = seed_project(repo)
    experiment = OptimizationExperimentRecord(
        experiment_id=new_id("experiment"),
        project_id=project.project_id,
        baseline_design_version_id=baseline.design_version_id,
    )
    candidate = CandidateRecord(
        candidate_id=new_id("candidate"),
        experiment_id=experiment.experiment_id,
        parent_design_version_id=baseline.design_version_id,
        parameter_changes={"c1_pf": 4.2},
        strategy="rule",
    )
    job = SimulationJobRecord(
        simulation_job_id=new_id("job"),
        project_id=project.project_id,
        candidate_ids=(candidate.candidate_id,),
        adapter_type="manual",
    )
    repo.add_experiment(experiment)
    repo.add_candidate(candidate)
    repo.add_simulation_job(job)

    updated_experiment = replace(experiment, strategy_config={"strategy": "hybrid"})
    updated_candidate = replace(candidate, evaluated_score=0.91)
    updated_job = replace(job, retryable=True, error_code="RESULT_CONTRACT_INVALID")
    repo.update_experiment(updated_experiment)
    repo.update_candidate(updated_candidate)
    repo.update_simulation_job(updated_job)

    assert repo.get_experiment(experiment.experiment_id) == updated_experiment
    assert repo.get_candidate(candidate.candidate_id) == updated_candidate
    assert repo.get_simulation_job(job.simulation_job_id) == updated_job


def test_phase2_migration_creates_workflow_tables(tmp_path):
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    table_names = set(inspect(make_engine(f"sqlite:///{database_path.as_posix()}")).get_table_names())
    assert {"comparisons", "optimization_experiments", "candidates", "simulation_jobs"} <= table_names

