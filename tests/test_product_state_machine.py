import pytest

from goa_eval.product.models import (
    AnalysisStatus,
    CandidateStatus,
    ExperimentStatus,
    SimulationJobStatus,
)
from goa_eval.product.state_machine import (
    InvalidTransition,
    transition_analysis,
    transition_candidate,
    transition_experiment,
    transition_simulation_job,
)


def test_candidate_can_be_approved():
    assert transition_candidate(
        CandidateStatus.PROPOSED,
        CandidateStatus.APPROVED,
    ) == CandidateStatus.APPROVED


def test_candidate_cannot_skip_resimulation():
    with pytest.raises(InvalidTransition) as exc_info:
        transition_candidate(
            CandidateStatus.PROPOSED,
            CandidateStatus.CONFIRMED_IMPROVEMENT,
        )

    assert exc_info.value.resource == "candidate"
    assert exc_info.value.current == CandidateStatus.PROPOSED
    assert exc_info.value.requested == CandidateStatus.CONFIRMED_IMPROVEMENT


def test_approved_candidate_cannot_be_confirmed_without_evaluation():
    with pytest.raises(InvalidTransition):
        transition_candidate(
            CandidateStatus.APPROVED,
            CandidateStatus.CONFIRMED_IMPROVEMENT,
        )


def test_failed_analysis_cannot_be_marked_completed():
    with pytest.raises(InvalidTransition):
        transition_analysis(AnalysisStatus.FAILED, AnalysisStatus.COMPLETED)


@pytest.mark.parametrize(
    "current",
    [ExperimentStatus.PAUSED, ExperimentStatus.WAITING_FOR_SIMULATION],
)
def test_paused_or_waiting_experiment_can_resume(current):
    assert transition_experiment(current, ExperimentStatus.RUNNING) == ExperimentStatus.RUNNING


def test_failed_simulation_job_can_be_explicitly_retried():
    assert transition_simulation_job(
        SimulationJobStatus.FAILED,
        SimulationJobStatus.QUEUED,
    ) == SimulationJobStatus.QUEUED
