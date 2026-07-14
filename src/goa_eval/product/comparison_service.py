from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import PurePosixPath
from typing import Any

from goa_eval.product.evidence_service import EvidenceService
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    CandidateRecord,
    CandidateStatus,
    ComparisonRecord,
    ComparisonVerdict,
    EvidenceRecord,
    new_id,
)
from goa_eval.product.state_machine import transition_candidate


class ComparisonClaimError(ValueError):
    pass


class ComparisonService:
    def __init__(self, repository: Any, artifact_store: Any) -> None:
        self._repository = repository
        self._artifact_store = artifact_store

    def compare_versions(
        self,
        project_id: str,
        baseline_version_id: str,
        result_version_id: str,
        baseline_run_id: str | None,
        result_run_id: str | None,
    ) -> ComparisonRecord:
        baseline_run = self._repository.get_analysis_run(baseline_run_id) if baseline_run_id else None
        result_run = self._repository.get_analysis_run(result_run_id) if result_run_id else None
        evidence = self._evidence_for_runs(baseline_run_id, result_run_id)
        verdict = ComparisonVerdict.EVIDENCE_INSUFFICIENT
        metric_deltas: dict[str, Any] = {}
        constraint_changes: dict[str, Any] = {}

        if self._runs_are_comparable(
            project_id,
            baseline_version_id,
            result_version_id,
            baseline_run,
            result_run,
            evidence,
        ):
            baseline_score = self._read_json(evidence[baseline_run_id]["score_summary.json"])
            result_score = self._read_json(evidence[result_run_id]["score_summary.json"])
            baseline_value = float(baseline_score["overall_score"])
            result_value = float(result_score["overall_score"])
            metric_deltas = {"overall_score": result_value - baseline_value}
            baseline_constraints = self._constraint_states(baseline_score)
            result_constraints = self._constraint_states(result_score)
            constraint_changes = {
                name: {
                    "baseline": baseline_constraints.get(name),
                    "result": result_constraints.get(name),
                }
                for name in sorted(set(baseline_constraints) | set(result_constraints))
            }
            verdict = self._verdict(baseline_value, result_value, baseline_constraints, result_constraints)

        record = ComparisonRecord(
            comparison_id=new_id("comparison"),
            project_id=project_id,
            baseline_design_version_id=baseline_version_id,
            result_design_version_id=result_version_id,
            baseline_analysis_run_id=baseline_run_id,
            result_analysis_run_id=result_run_id,
            metric_deltas=metric_deltas,
            constraint_changes=constraint_changes,
            evidence_ids=tuple(
                item.evidence_id
                for run_evidence in evidence.values()
                for item in run_evidence.values()
            ),
            verdict=verdict,
        )
        self._repository.add_comparison(record)
        return record

    def confirm_candidate(self, candidate_id: str, comparison_id: str) -> CandidateRecord:
        candidate = self._repository.get_candidate(candidate_id)
        comparison = self._repository.get_comparison(comparison_id)
        if candidate is None or comparison is None:
            raise ComparisonClaimError("candidate or comparison was not found")
        result_run = (
            self._repository.get_analysis_run(comparison.result_analysis_run_id)
            if comparison.result_analysis_run_id
            else None
        )
        job = (
            self._repository.get_simulation_job(candidate.simulation_job_id)
            if candidate.simulation_job_id
            else None
        )
        if result_run is None or job is None or job.result_ref is None:
            raise ComparisonClaimError("evaluated result provenance is incomplete")
        provenance = json.loads(self._artifact_store.resolve(job.result_ref).read_text(encoding="utf-8"))
        if provenance.get("candidate_id") != candidate.candidate_id:
            raise ComparisonClaimError("candidate provenance does not match")
        if provenance.get("simulation_job_id") != job.simulation_job_id:
            raise ComparisonClaimError("simulation job provenance does not match")
        if job.result_sha256 and provenance.get("result_sha256") != job.result_sha256:
            raise ComparisonClaimError("result checksum provenance does not match")
        if candidate.result_design_version_id != comparison.result_design_version_id:
            raise ComparisonClaimError("result design version does not match comparison")
        if not self._matching_complete_boundaries(comparison, result_run):
            raise ComparisonClaimError("comparison evidence boundary does not match")
        if not EvidenceService.can_confirm_improvement(
            self._candidate_mapping(candidate),
            result_run,
            asdict(comparison),
            provenance,
        ):
            raise ComparisonClaimError("candidate is not eligible for confirmed improvement")

        updated = replace(
            candidate,
            status=transition_candidate(candidate.status, CandidateStatus.CONFIRMED_IMPROVEMENT),
        )
        self._repository.update_candidate(updated)
        return updated

    def _runs_are_comparable(
        self,
        project_id: str,
        baseline_version_id: str,
        result_version_id: str,
        baseline_run: AnalysisRunRecord | None,
        result_run: AnalysisRunRecord | None,
        evidence: dict[str, dict[str, EvidenceRecord]],
    ) -> bool:
        if baseline_run is None or result_run is None:
            return False
        baseline_version = self._repository.get_design_version(baseline_version_id)
        result_version = self._repository.get_design_version(result_version_id)
        if baseline_version is None or result_version is None:
            return False
        if baseline_version.project_id != project_id or result_version.project_id != project_id:
            return False
        if baseline_run.design_version_id != baseline_version_id or result_run.design_version_id != result_version_id:
            return False
        if baseline_run.status != AnalysisStatus.COMPLETED or result_run.status != AnalysisStatus.COMPLETED:
            return False
        if baseline_run.evidence_boundary != result_run.evidence_boundary:
            return False
        required = {"real_summary.json", "score_summary.json", "real_metrics.csv"}
        if not required <= set(evidence.get(baseline_run.analysis_run_id, {})):
            return False
        if not required <= set(evidence.get(result_run.analysis_run_id, {})):
            return False
        try:
            self._read_json(evidence[baseline_run.analysis_run_id]["real_summary.json"])
            self._read_json(evidence[result_run.analysis_run_id]["real_summary.json"])
            self._read_text(evidence[baseline_run.analysis_run_id]["real_metrics.csv"])
            self._read_text(evidence[result_run.analysis_run_id]["real_metrics.csv"])
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return True

    def _matching_complete_boundaries(self, comparison: ComparisonRecord, result_run: AnalysisRunRecord) -> bool:
        if comparison.verdict != ComparisonVerdict.IMPROVED or result_run.status != AnalysisStatus.COMPLETED:
            return False
        baseline_run = (
            self._repository.get_analysis_run(comparison.baseline_analysis_run_id)
            if comparison.baseline_analysis_run_id
            else None
        )
        return bool(
            baseline_run is not None
            and baseline_run.status == AnalysisStatus.COMPLETED
            and baseline_run.evidence_boundary == result_run.evidence_boundary
        )

    def _evidence_for_runs(self, *run_ids: str | None) -> dict[str, dict[str, EvidenceRecord]]:
        result: dict[str, dict[str, EvidenceRecord]] = {}
        for run_id in run_ids:
            if not run_id:
                continue
            result[run_id] = {
                PurePosixPath(record.source_ref.removeprefix("artifact://")).name: record
                for record in self._repository.list_evidence("analysis_run", run_id)
            }
        return result

    def _read_text(self, evidence: EvidenceRecord) -> str:
        ref = self._artifact_store.ref_from_uri(evidence.source_ref, evidence.checksum)
        return self._artifact_store.resolve(ref).read_text(encoding="utf-8")

    def _read_json(self, evidence: EvidenceRecord) -> dict[str, Any]:
        return json.loads(self._read_text(evidence))

    @staticmethod
    def _constraint_states(score: dict[str, Any]) -> dict[str, bool]:
        states: dict[str, bool] = {}
        for name, payload in (score.get("hard_constraints") or {}).items():
            states[str(name)] = bool(payload.get("passed")) if isinstance(payload, dict) else bool(payload)
        if not states and "hard_constraint_passed" in score:
            states["all"] = bool(score["hard_constraint_passed"])
        return states

    @staticmethod
    def _verdict(
        baseline_score: float,
        result_score: float,
        baseline_constraints: dict[str, bool],
        result_constraints: dict[str, bool],
    ) -> ComparisonVerdict:
        names = set(baseline_constraints) | set(result_constraints)
        if any(baseline_constraints.get(name, False) and not result_constraints.get(name, False) for name in names):
            return ComparisonVerdict.REGRESSED
        if result_score > baseline_score + 1e-12:
            return ComparisonVerdict.IMPROVED
        if result_score < baseline_score - 1e-12:
            return ComparisonVerdict.REGRESSED
        return ComparisonVerdict.NEUTRAL

    @staticmethod
    def _candidate_mapping(candidate: CandidateRecord) -> dict[str, Any]:
        data = asdict(candidate)
        data["status"] = candidate.status.value
        return data
