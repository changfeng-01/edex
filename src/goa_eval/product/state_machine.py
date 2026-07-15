from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from goa_eval.product.models import (
    AnalysisStatus,
    CandidateStatus,
    ExperimentStatus,
    SimulationJobStatus,
)


StatusT = TypeVar("StatusT", bound=Enum)


@dataclass(frozen=True)
class InvalidTransition(ValueError):
    resource: str
    current: Enum
    requested: Enum

    def __str__(self) -> str:
        return f"invalid {self.resource} transition: {self.current.value} -> {self.requested.value}"


ANALYSIS_TRANSITIONS = {
    AnalysisStatus.DRAFT: {AnalysisStatus.PREVIEWED, AnalysisStatus.QUEUED, AnalysisStatus.FAILED},
    AnalysisStatus.PREVIEWED: {AnalysisStatus.QUEUED, AnalysisStatus.FAILED},
    AnalysisStatus.QUEUED: {AnalysisStatus.RUNNING, AnalysisStatus.FAILED},
    AnalysisStatus.RUNNING: {
        AnalysisStatus.COMPLETED,
        AnalysisStatus.FAILED,
        AnalysisStatus.EVIDENCE_INCOMPLETE,
    },
    AnalysisStatus.COMPLETED: {AnalysisStatus.EVIDENCE_INCOMPLETE},
    AnalysisStatus.FAILED: set(),
    AnalysisStatus.EVIDENCE_INCOMPLETE: set(),
}

CANDIDATE_TRANSITIONS = {
    CandidateStatus.PROPOSED: {CandidateStatus.APPROVED, CandidateStatus.REJECTED},
    CandidateStatus.APPROVED: {CandidateStatus.SIMULATION_PENDING, CandidateStatus.REJECTED},
    CandidateStatus.REJECTED: set(),
    CandidateStatus.SIMULATION_PENDING: {
        CandidateStatus.SIMULATION_FAILED,
        CandidateStatus.RESIMULATED,
    },
    CandidateStatus.SIMULATION_FAILED: {CandidateStatus.SIMULATION_PENDING},
    CandidateStatus.RESIMULATED: {CandidateStatus.EVALUATED},
    CandidateStatus.EVALUATED: {
        CandidateStatus.CONFIRMED_IMPROVEMENT,
        CandidateStatus.REGRESSED,
        CandidateStatus.NEUTRAL,
    },
    CandidateStatus.CONFIRMED_IMPROVEMENT: set(),
    CandidateStatus.REGRESSED: set(),
    CandidateStatus.NEUTRAL: set(),
}

EXPERIMENT_TRANSITIONS = {
    ExperimentStatus.DRAFT: {ExperimentStatus.READY, ExperimentStatus.TERMINATED},
    ExperimentStatus.READY: {ExperimentStatus.RUNNING, ExperimentStatus.TERMINATED},
    ExperimentStatus.RUNNING: {
        ExperimentStatus.WAITING_FOR_SIMULATION,
        ExperimentStatus.PAUSED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.TERMINATED,
    },
    ExperimentStatus.WAITING_FOR_SIMULATION: {
        ExperimentStatus.RUNNING,
        ExperimentStatus.PAUSED,
        ExperimentStatus.FAILED,
        ExperimentStatus.TERMINATED,
    },
    ExperimentStatus.PAUSED: {ExperimentStatus.RUNNING, ExperimentStatus.TERMINATED},
    ExperimentStatus.COMPLETED: set(),
    ExperimentStatus.FAILED: set(),
    ExperimentStatus.TERMINATED: set(),
}

SIMULATION_JOB_TRANSITIONS = {
    SimulationJobStatus.DRAFT: {SimulationJobStatus.EXPORTED, SimulationJobStatus.QUEUED},
    SimulationJobStatus.EXPORTED: {
        SimulationJobStatus.WAITING_FOR_RESULTS,
        SimulationJobStatus.QUEUED,
        SimulationJobStatus.COMPLETED,
        SimulationJobStatus.FAILED,
    },
    SimulationJobStatus.WAITING_FOR_RESULTS: {
        SimulationJobStatus.VALIDATING,
        SimulationJobStatus.FAILED,
    },
    SimulationJobStatus.VALIDATING: {
        SimulationJobStatus.COMPLETED,
        SimulationJobStatus.FAILED,
    },
    SimulationJobStatus.QUEUED: {SimulationJobStatus.RUNNING, SimulationJobStatus.FAILED},
    SimulationJobStatus.RUNNING: {
        SimulationJobStatus.WAITING_FOR_RESULTS,
        SimulationJobStatus.COMPLETED,
        SimulationJobStatus.FAILED,
    },
    SimulationJobStatus.COMPLETED: set(),
    SimulationJobStatus.FAILED: {
        SimulationJobStatus.QUEUED,
        SimulationJobStatus.WAITING_FOR_RESULTS,
    },
}


def _transition(resource: str, current: StatusT, requested: StatusT, transitions: dict[StatusT, set[StatusT]]) -> StatusT:
    if requested not in transitions[current]:
        raise InvalidTransition(resource, current, requested)
    return requested


def transition_analysis(current: AnalysisStatus, requested: AnalysisStatus) -> AnalysisStatus:
    return _transition("analysis", current, requested, ANALYSIS_TRANSITIONS)


def transition_candidate(current: CandidateStatus, requested: CandidateStatus) -> CandidateStatus:
    return _transition("candidate", current, requested, CANDIDATE_TRANSITIONS)


def transition_experiment(current: ExperimentStatus, requested: ExperimentStatus) -> ExperimentStatus:
    return _transition("experiment", current, requested, EXPERIMENT_TRANSITIONS)


def transition_simulation_job(
    current: SimulationJobStatus,
    requested: SimulationJobStatus,
) -> SimulationJobStatus:
    return _transition("simulation_job", current, requested, SIMULATION_JOB_TRANSITIONS)
