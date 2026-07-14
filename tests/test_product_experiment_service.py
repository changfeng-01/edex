from dataclasses import replace

import pytest

from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import (
    CandidateStatus,
    ExperimentStatus,
    ProjectRecord,
    WorkspaceRecord,
    DesignVersionRecord,
    new_id,
)
from goa_eval.product.repositories import SqlAlchemyProductRepository
from goa_eval.product.state_machine import InvalidTransition


@pytest.fixture
def experiment_context(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repository = SqlAlchemyProductRepository(engine)
    workspace = WorkspaceRecord(new_id("workspace"), "GOA team")
    project = ProjectRecord(
        new_id("project"),
        workspace.workspace_id,
        "GOA",
        "goa_8k",
        "spec_v1",
    )
    baseline = DesignVersionRecord(new_id("version"), project.project_id, "baseline")
    repository.add_workspace(workspace)
    repository.add_project(project)
    repository.add_design_version(baseline)
    return repository, project, baseline


def deterministic_generator(config, max_candidates, seed):
    offset = int(config.get("offset", 0))
    return [
        {
            "parameter_changes": {"t1_width_um": offset + seed + index},
            "reason_codes": ["reduce_ripple"],
            "selection_score": 0.9 - index * 0.1,
        }
        for index in range(max_candidates)
    ]


def test_create_and_generate_are_deterministic_and_persisted(experiment_context):
    from goa_eval.product.experiment_service import ExperimentService

    repository, project, baseline = experiment_context
    service = ExperimentService(repository, generators={"rule": deterministic_generator})
    experiment = service.create_experiment(
        project.project_id,
        baseline.design_version_id,
        {"strategy": "rule", "offset": 3},
    )

    first = service.generate_candidates(experiment.experiment_id, "rule", 2, 17)
    second = service.generate_candidates(experiment.experiment_id, "rule", 2, 17)

    assert experiment.state == ExperimentStatus.READY
    assert first == second
    assert len(first) == 2
    assert all(candidate.parent_design_version_id == baseline.design_version_id for candidate in first)
    assert all(candidate.must_resimulate is True for candidate in first)
    assert first[0].selection_score == 0.9
    assert repository.list_candidates(experiment.experiment_id) == first


def test_generation_refuses_changed_seed_after_candidates_are_persisted(experiment_context):
    from goa_eval.product.experiment_service import ExperimentConflict, ExperimentService

    repository, project, baseline = experiment_context
    service = ExperimentService(repository, generators={"rule": deterministic_generator})
    experiment = service.create_experiment(project.project_id, baseline.design_version_id, {"strategy": "rule"})
    service.generate_candidates(experiment.experiment_id, "rule", 1, 17)

    with pytest.raises(ExperimentConflict, match="seed"):
        service.generate_candidates(experiment.experiment_id, "rule", 1, 18)


def test_approve_and_reject_are_explicit_idempotent_and_audited(experiment_context):
    from goa_eval.product.experiment_service import ExperimentService

    repository, project, baseline = experiment_context
    service = ExperimentService(repository, generators={"rule": deterministic_generator})
    experiment = service.create_experiment(project.project_id, baseline.design_version_id, {"strategy": "rule"})
    candidates = service.generate_candidates(experiment.experiment_id, "rule", 2, 7)

    approved = service.approve_candidate(candidates[0].candidate_id, "reviewer_1")
    approved_again = service.approve_candidate(candidates[0].candidate_id, "reviewer_1")
    rejected = service.reject_candidate(candidates[1].candidate_id, "reviewer_2", "unsafe direction")

    assert approved.status == CandidateStatus.APPROVED
    assert approved_again == approved
    assert rejected.status == CandidateStatus.REJECTED
    approve_events = repository.list_audit_events("candidate", approved.candidate_id)
    reject_events = repository.list_audit_events("candidate", rejected.candidate_id)
    assert [(event.actor_id, event.action) for event in approve_events] == [("reviewer_1", "candidate.approved")]
    assert [(event.actor_id, event.action) for event in reject_events] == [("reviewer_2", "candidate.rejected")]
    assert reject_events[0].details["reason"] == "unsafe direction"


def test_illegal_candidate_status_cannot_be_approved(experiment_context):
    from goa_eval.product.experiment_service import ExperimentService

    repository, project, baseline = experiment_context
    service = ExperimentService(repository, generators={"rule": deterministic_generator})
    experiment = service.create_experiment(project.project_id, baseline.design_version_id, {"strategy": "rule"})
    candidate = service.generate_candidates(experiment.experiment_id, "rule", 1, 7)[0]
    repository.update_candidate(replace(candidate, status=CandidateStatus.EVALUATED))

    with pytest.raises(InvalidTransition):
        service.approve_candidate(candidate.candidate_id, "reviewer_1")


@pytest.mark.parametrize("state", [ExperimentStatus.PAUSED, ExperimentStatus.WAITING_FOR_SIMULATION])
def test_resume_experiment_preserves_candidates(experiment_context, state):
    from goa_eval.product.experiment_service import ExperimentService

    repository, project, baseline = experiment_context
    service = ExperimentService(repository, generators={"rule": deterministic_generator})
    experiment = service.create_experiment(project.project_id, baseline.design_version_id, {"strategy": "rule"})
    candidates = service.generate_candidates(experiment.experiment_id, "rule", 1, 7)
    repository.update_experiment(replace(repository.get_experiment(experiment.experiment_id), state=state))

    resumed = service.resume_experiment(experiment.experiment_id)

    assert resumed.state == ExperimentStatus.RUNNING
    assert repository.list_candidates(experiment.experiment_id) == candidates

