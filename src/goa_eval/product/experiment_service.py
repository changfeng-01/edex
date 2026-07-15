from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping

import pandas as pd

from goa_eval.product.models import (
    AuditEventRecord,
    CandidateRecord,
    CandidateStatus,
    ExperimentStatus,
    OptimizationExperimentRecord,
    new_id,
)
from goa_eval.product.state_machine import transition_candidate, transition_experiment


CandidateGenerator = Callable[[Mapping[str, Any], int, int], list[dict[str, Any]]]


class ExperimentNotFound(KeyError):
    pass


class ExperimentConflict(ValueError):
    pass


class ExperimentService:
    def __init__(
        self,
        repository: Any,
        *,
        generators: Mapping[str, CandidateGenerator] | None = None,
        pia_adapter: Any | None = None,
    ) -> None:
        self._repository = repository
        self._generators = dict(generators or self._default_generators())
        self._pia_adapter = pia_adapter

    def create_experiment(
        self,
        project_id: str,
        baseline_version_id: str,
        strategy_config: Mapping[str, Any],
    ) -> OptimizationExperimentRecord:
        project = self._repository.get_project(project_id)
        baseline = self._repository.get_design_version(baseline_version_id)
        if project is None or baseline is None or baseline.project_id != project_id:
            raise ExperimentNotFound("project or baseline design version was not found")
        record = OptimizationExperimentRecord(
            experiment_id=new_id("experiment"),
            project_id=project_id,
            baseline_design_version_id=baseline_version_id,
            strategy_config=dict(strategy_config),
            state=ExperimentStatus.READY,
        )
        self._repository.add_experiment(record)
        self._audit("system", "experiment.created", "experiment", record.experiment_id, {})
        return record

    def generate_candidates(
        self,
        experiment_id: str,
        strategy: str,
        max_candidates: int,
        seed: int,
    ) -> list[CandidateRecord]:
        experiment = self._require_experiment(experiment_id)
        existing = self._repository.list_candidates(experiment_id)
        if existing:
            contract = experiment.strategy_config.get("generation_contract", {})
            if int(contract.get("seed", experiment.seed if experiment.seed is not None else seed)) != seed:
                raise ExperimentConflict("candidate generation seed differs from the persisted seed")
            if str(contract.get("strategy", strategy)) != strategy or int(
                contract.get("max_candidates", len(existing))
            ) != max_candidates:
                raise ExperimentConflict("candidate generation contract differs from persisted candidates")
            return existing
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        generator = self._generators.get(strategy)
        if generator is None:
            raise ValueError(f"unsupported candidate strategy: {strategy}")
        proposals = generator(experiment.strategy_config, max_candidates, seed)[:max_candidates]
        candidates = [self._candidate_from_proposal(experiment, strategy, proposal) for proposal in proposals]
        for candidate in candidates:
            self._repository.add_candidate(candidate)
        config = dict(experiment.strategy_config)
        config["generation_contract"] = {
            "strategy": strategy,
            "max_candidates": max_candidates,
            "seed": seed,
        }
        updated = replace(experiment, strategy_config=config, seed=seed, budget=max_candidates)
        self._repository.update_experiment(updated)
        self._audit(
            "system",
            "experiment.candidates_generated",
            "experiment",
            experiment_id,
            {"strategy": strategy, "seed": seed, "candidate_count": len(candidates)},
        )
        return candidates

    def approve_candidate(self, candidate_id: str, actor_id: str) -> CandidateRecord:
        candidate = self._require_candidate(candidate_id)
        if candidate.status == CandidateStatus.APPROVED:
            return candidate
        updated = replace(
            candidate,
            status=transition_candidate(candidate.status, CandidateStatus.APPROVED),
        )
        self._repository.update_candidate(updated)
        self._audit(actor_id, "candidate.approved", "candidate", candidate_id, {})
        return updated

    def reject_candidate(self, candidate_id: str, actor_id: str, reason: str) -> CandidateRecord:
        candidate = self._require_candidate(candidate_id)
        if candidate.status == CandidateStatus.REJECTED:
            return candidate
        updated = replace(
            candidate,
            status=transition_candidate(candidate.status, CandidateStatus.REJECTED),
        )
        self._repository.update_candidate(updated)
        self._audit(actor_id, "candidate.rejected", "candidate", candidate_id, {"reason": reason})
        return updated

    def resume_experiment(self, experiment_id: str) -> OptimizationExperimentRecord:
        experiment = self._require_experiment(experiment_id)
        if experiment.state == ExperimentStatus.RUNNING:
            return experiment
        updated = replace(
            experiment,
            state=transition_experiment(experiment.state, ExperimentStatus.RUNNING),
        )
        self._repository.update_experiment(updated)
        self._audit("system", "experiment.resumed", "experiment", experiment_id, {})
        return updated

    def run_pia_evolution(self, experiment_id: str, **kwargs: Any) -> Any:
        self._require_experiment(experiment_id)
        if self._pia_adapter is None:
            raise ExperimentConflict("PIA evolution adapter is not configured")
        return self._pia_adapter.run(experiment_id, **kwargs)

    def _require_experiment(self, experiment_id: str) -> OptimizationExperimentRecord:
        experiment = self._repository.get_experiment(experiment_id)
        if experiment is None:
            raise ExperimentNotFound(experiment_id)
        return experiment

    def _require_candidate(self, candidate_id: str) -> CandidateRecord:
        candidate = self._repository.get_candidate(candidate_id)
        if candidate is None:
            raise ExperimentNotFound(candidate_id)
        return candidate

    def _candidate_from_proposal(
        self,
        experiment: OptimizationExperimentRecord,
        strategy: str,
        proposal: Mapping[str, Any],
    ) -> CandidateRecord:
        changes = proposal.get("parameter_changes")
        if not isinstance(changes, dict) or not changes:
            raise ValueError("candidate proposal requires parameter_changes")
        reasons = proposal.get("reason_codes", ())
        return CandidateRecord(
            candidate_id=new_id("candidate"),
            experiment_id=experiment.experiment_id,
            parent_design_version_id=experiment.baseline_design_version_id,
            parameter_changes=dict(changes),
            strategy=strategy,
            reason_codes=tuple(str(reason) for reason in reasons),
            selection_score=self._float_or_none(proposal.get("selection_score")),
            selection_scores=dict(proposal.get("selection_scores") or {}),
            must_resimulate=True,
        )

    def _audit(
        self,
        actor_id: str,
        action: str,
        subject_type: str,
        subject_id: str,
        details: dict[str, Any],
    ) -> None:
        self._repository.append_audit_event(
            AuditEventRecord(
                event_id=new_id("event"),
                actor_id=actor_id,
                action=action,
                subject_type=subject_type,
                subject_id=subject_id,
                details=details,
            )
        )

    @staticmethod
    def _default_generators() -> dict[str, CandidateGenerator]:
        return {
            "rule": _rule_candidates,
            "hybrid": _hybrid_candidates,
            "pia": _pia_candidates,
        }

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def _rule_candidates(config: Mapping[str, Any], max_candidates: int, seed: int) -> list[dict[str, Any]]:
    del seed
    from goa_eval.multi_agent.tools import generate_candidates

    leaderboard_path = _required_path(config, "leaderboard_path")
    param_space_path = _required_path(config, "param_space_path")
    with TemporaryDirectory(prefix="circuitpilot-rule-candidates-") as temporary:
        result = generate_candidates(leaderboard_path, param_space_path, temporary, max_candidates=max_candidates)
        frame = pd.read_csv(result.data["next_candidates_path"])
    return [_proposal_from_row(row) for row in frame.to_dict(orient="records")]


def _hybrid_candidates(config: Mapping[str, Any], max_candidates: int, seed: int) -> list[dict[str, Any]]:
    from goa_eval.goa_hybrid_optimizer import run_hybrid_goa_optimizer

    with TemporaryDirectory(prefix="circuitpilot-hybrid-candidates-") as temporary:
        output = Path(temporary)
        run_hybrid_goa_optimizer(
            history_path=_optional_path(config.get("history_path")),
            leaderboard_path=_optional_path(config.get("leaderboard_path")),
            param_space_path=_optional_path(config.get("param_space_path")),
            output_root=output,
            max_candidates=max_candidates,
            seed=seed,
        )
        frame = pd.read_csv(output / "hybrid_candidates.csv")
    return [_proposal_from_row(row) for row in frame.to_dict(orient="records")]


def _pia_candidates(config: Mapping[str, Any], max_candidates: int, seed: int) -> list[dict[str, Any]]:
    del seed
    from goa_eval.pia_ca_llso.loop import suggest_next_run

    history = pd.read_csv(_required_path(config, "history_path"))
    candidates = pd.read_csv(_required_path(config, "candidate_pool_path"))
    result = suggest_next_run(
        history,
        candidates,
        dict(config.get("pia_config") or {}),
        str(config.get("pia_strategy") or "pia_capm_distance"),
        max_candidates,
    )
    return [_proposal_from_row(row) for row in result.selected_candidates.to_dict(orient="records")]


def _proposal_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    changes = row.get("parameter_changes")
    if not isinstance(changes, dict):
        parameters = _json_object(row.get("parameters_json"))
        if parameters:
            changes = parameters
        elif row.get("parameter") is not None:
            values = _json_value(row.get("candidate_values"))
            value = values[0] if isinstance(values, list) and values else values
            changes = {str(row["parameter"]): value}
        else:
            raise ValueError("optimizer output does not contain parameter changes")
    reasons = [
        str(value)
        for value in (row.get("trigger_metric"), row.get("candidate_source"), row.get("source_recommendation"))
        if value is not None and str(value) not in {"", "nan"}
    ]
    score = row.get("selection_score", row.get("predicted_overall_score", row.get("candidate_quality_proxy")))
    return {
        "parameter_changes": changes,
        "reason_codes": reasons,
        "selection_score": score,
    }


def _json_object(value: Any) -> dict[str, Any]:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, dict) else {}


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _required_path(config: Mapping[str, Any], key: str) -> Path:
    path = _optional_path(config.get(key))
    if path is None or not path.is_file():
        raise ValueError(f"strategy config requires an existing {key}")
    return path


def _optional_path(value: Any) -> Path | None:
    return Path(value) if value else None
