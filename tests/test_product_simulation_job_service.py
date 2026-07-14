import json
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.models import CandidateStatus, SimulationJobStatus
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository


def generator(_config, max_candidates, seed):
    return [
        {
            "parameter_changes": {"t1_width_um": 10.0 + seed + index, "c1_pf": 4.0},
            "reason_codes": ["reduce_ripple"],
            "selection_score": 0.9 - index * 0.1,
        }
        for index in range(max_candidates)
    ]


@pytest.fixture
def simulation_context(tmp_path):
    repository = SqlAlchemyProductRepository(make_engine(f"sqlite:///{tmp_path / 'product.db'}"))
    create_schema(repository._sessions.kw["bind"])
    store = LocalArtifactStore(tmp_path / "artifacts")
    projects = ProjectService(repository, store)
    workspace = projects.create_workspace("GOA team")
    project = projects.create_project(workspace.workspace_id, "GOA", "goa_8k", "spec_v1").project
    baseline = projects.create_design_version(project.project_id, "baseline")
    experiments = ExperimentService(repository, generators={"rule": generator})
    experiment = experiments.create_experiment(project.project_id, baseline.design_version_id, {"strategy": "rule"})
    candidates = experiments.generate_candidates(experiment.experiment_id, "rule", 2, 7)
    return repository, store, projects, experiments, project, baseline, candidates, tmp_path


def test_only_approved_candidates_export_and_repeated_export_is_idempotent(simulation_context):
    from goa_eval.product.simulation_job_service import SimulationJobConflict, SimulationJobService

    repository, store, projects, experiments, _, _, candidates, _ = simulation_context
    service = SimulationJobService(repository, store, projects)
    with pytest.raises(SimulationJobConflict, match="approved"):
        service.create_manual_job([candidates[0].candidate_id])

    approved = experiments.approve_candidate(candidates[0].candidate_id, "reviewer")
    job = service.create_manual_job([approved.candidate_id])
    first = service.export_job(job.simulation_job_id)
    second = service.export_job(job.simulation_job_id)

    assert first == second
    assert first.status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert first.batch_ref is not None
    batch = pd.read_csv(store.resolve(first.batch_ref))
    assert batch["candidate_id"].tolist() == [approved.candidate_id]
    assert batch["must_resimulate"].eq(True).all()
    assert batch["data_source"].eq("real_simulation_csv").all()
    assert "parameter_hash" in batch.columns


def test_preview_commit_and_restart_are_resumable(simulation_context):
    from goa_eval.product.simulation_job_service import SimulationJobService

    repository, store, projects, experiments, _, baseline, candidates, tmp_path = simulation_context
    approved = experiments.approve_candidate(candidates[0].candidate_id, "reviewer")
    service = SimulationJobService(repository, store, projects)
    job = service.export_job(service.create_manual_job([approved.candidate_id]).simulation_job_id)
    batch = pd.read_csv(store.resolve(job.batch_ref))
    result_path = tmp_path / "result.csv"
    pd.DataFrame(
        {
            "candidate_id": batch["candidate_id"],
            "parameter_hash": batch["parameter_hash"],
            "overall_score": [0.88],
            "hard_constraint_passed": [True],
        }
    ).to_csv(result_path, index=False)

    preview = service.preview_import(job.simulation_job_id, result_path)
    restarted = SimulationJobService(repository, store, projects)
    completed = restarted.commit_import(job.simulation_job_id, preview.manifest_sha256)

    candidate = repository.get_candidate(approved.candidate_id)
    result_version = repository.get_design_version(candidate.result_design_version_id)
    manifest = json.loads(store.resolve(completed.result_ref).read_text(encoding="utf-8"))
    assert completed.status == SimulationJobStatus.COMPLETED
    assert candidate.status == CandidateStatus.RESIMULATED
    assert result_version.parent_version_id == baseline.design_version_id
    assert result_version.source_candidate_id == candidate.candidate_id
    assert manifest["candidate_ids"] == [candidate.candidate_id]
    assert manifest["simulation_job_id"] == job.simulation_job_id
    assert manifest["data_source"] == "real_simulation_csv"
    assert manifest["engineering_validity"] == "simulation_only"
    assert manifest["must_resimulate"] is True
    assert restarted.commit_import(job.simulation_job_id, preview.manifest_sha256) == completed


@pytest.mark.parametrize(
    "mutation",
    [
        lambda frame: frame.assign(candidate_id="candidate_unknown"),
        lambda frame: frame.drop(columns=["overall_score"]),
        lambda frame: frame.assign(parameter_hash="bad-hash"),
    ],
)
def test_invalid_import_is_quarantined_and_fails_closed(simulation_context, mutation):
    from goa_eval.product.simulation_job_service import SimulationImportError, SimulationJobService

    repository, store, projects, experiments, _, _, candidates, tmp_path = simulation_context
    approved = experiments.approve_candidate(candidates[0].candidate_id, "reviewer")
    service = SimulationJobService(repository, store, projects)
    job = service.export_job(service.create_manual_job([approved.candidate_id]).simulation_job_id)
    batch = pd.read_csv(store.resolve(job.batch_ref))
    frame = pd.DataFrame(
        {
            "candidate_id": batch["candidate_id"],
            "parameter_hash": batch["parameter_hash"],
            "overall_score": [0.88],
            "hard_constraint_passed": [True],
        }
    )
    path = tmp_path / "invalid.csv"
    mutation(frame).to_csv(path, index=False)

    with pytest.raises(SimulationImportError):
        service.preview_import(job.simulation_job_id, path)

    failed = repository.get_simulation_job(job.simulation_job_id)
    assert failed.status == SimulationJobStatus.FAILED
    assert failed.result_ref is not None
    assert store.exists(failed.result_ref)
    assert failed.retryable is True


def test_retry_increments_attempt_and_preserves_audit(simulation_context):
    from goa_eval.product.simulation_job_service import SimulationImportError, SimulationJobService

    repository, store, projects, experiments, _, _, candidates, tmp_path = simulation_context
    approved = experiments.approve_candidate(candidates[0].candidate_id, "reviewer")
    service = SimulationJobService(repository, store, projects)
    job = service.export_job(service.create_manual_job([approved.candidate_id]).simulation_job_id)
    bad = tmp_path / "bad.csv"
    bad.write_text("candidate_id\nwrong\n", encoding="utf-8")
    with pytest.raises(SimulationImportError):
        service.preview_import(job.simulation_job_id, bad)

    retried = service.retry_job(job.simulation_job_id)

    assert retried.status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert retried.import_attempt == 2
    actions = [event.action for event in repository.list_audit_events("simulation_job", job.simulation_job_id)]
    assert actions == [
        "simulation_job.created",
        "simulation_job.exported",
        "simulation_job.import_failed",
        "simulation_job.retried",
    ]


def test_preview_rejects_traversal_source_path(simulation_context):
    from goa_eval.product.simulation_job_service import SimulationImportError, SimulationJobService

    repository, store, projects, experiments, _, _, candidates, _ = simulation_context
    approved = experiments.approve_candidate(candidates[0].candidate_id, "reviewer")
    service = SimulationJobService(repository, store, projects)
    job = service.export_job(service.create_manual_job([approved.candidate_id]).simulation_job_id)

    with pytest.raises(SimulationImportError, match="path"):
        service.preview_import(job.simulation_job_id, Path("..") / "outside.csv")

