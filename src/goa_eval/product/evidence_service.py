from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from goa_eval.product.artifact_store import ArtifactRef
from goa_eval.product.models import (
    AnalysisRunRecord,
    AnalysisStatus,
    EvidenceBoundary,
    EvidenceIndexSummary,
    EvidenceRecord,
    new_id,
)
from goa_eval.product_demo.schemas import normalize_evidence_boundary


REQUIRED_EVIDENCE_FILES = (
    "real_summary.json",
    "score_summary.json",
    "real_metrics.csv",
    "recommendations.md",
    "issues.json",
    "run_manifest.json",
)


class EvidenceBoundaryInvalid(ValueError):
    pass


class EvidenceService:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def index_analysis_artifacts(
        self,
        run_id: str,
        artifact_refs: Iterable[ArtifactRef],
        raw_evidence: Mapping[str, Any] | None,
    ) -> EvidenceIndexSummary:
        boundary_data = self.validate_boundary(raw_evidence or {})
        boundary = EvidenceBoundary(
            data_source=str(boundary_data["data_source"]),
            engineering_validity=str(boundary_data["engineering_validity"]),
            must_resimulate=bool(boundary_data["must_resimulate"]),
        )
        refs = tuple(artifact_refs)
        records = []
        for ref in refs:
            record = EvidenceRecord(
                evidence_id=new_id("evidence"),
                subject_type="analysis_run",
                subject_id=run_id,
                evidence_type=ref.key,
                source_ref=ref.uri,
                checksum=ref.sha256,
                boundary=boundary,
            )
            self._repository.add_evidence(record)
            records.append(record)
        present = {PurePosixPath(ref.key).name for ref in refs}
        missing = tuple(name for name in REQUIRED_EVIDENCE_FILES if name not in present)
        return EvidenceIndexSummary(
            run_id=run_id,
            completeness="incomplete" if missing else "complete",
            evidence_ids=tuple(record.evidence_id for record in records),
            missing_required=missing,
        )

    def validate_boundary(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        return normalize_evidence_boundary(evidence)

    def summarize_completeness(
        self,
        run_id: str,
        *,
        raw_evidence: Mapping[str, Any] | None = None,
    ) -> EvidenceIndexSummary:
        try:
            if raw_evidence is not None:
                self.validate_boundary(raw_evidence)
        except EvidenceBoundaryInvalid as exc:
            return EvidenceIndexSummary(
                run_id=run_id,
                completeness="invalid",
                invalid_reasons=(str(exc),),
            )
        records = self._repository.list_evidence("analysis_run", run_id)
        present = {PurePosixPath(record.source_ref.removeprefix("artifact://")).name for record in records}
        missing = tuple(name for name in REQUIRED_EVIDENCE_FILES if name not in present)
        return EvidenceIndexSummary(
            run_id=run_id,
            completeness="incomplete" if missing else "complete",
            evidence_ids=tuple(record.evidence_id for record in records),
            missing_required=missing,
        )

    @staticmethod
    def can_confirm_improvement(
        candidate: Mapping[str, Any],
        result_run: AnalysisRunRecord,
        comparison: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> bool:
        if candidate.get("readonly") is True:
            return False
        if comparison is None or provenance is None:
            return False
        status = getattr(candidate.get("status"), "value", candidate.get("status"))
        verdict = getattr(comparison.get("verdict"), "value", comparison.get("verdict"))
        return bool(
            status == "evaluated"
            and result_run.status == AnalysisStatus.COMPLETED
            and candidate.get("result_design_version_id") == result_run.design_version_id
            and comparison.get("result_analysis_run_id") == result_run.analysis_run_id
            and verdict == "improved"
            and provenance.get("candidate_id") == candidate.get("candidate_id")
            and provenance.get("simulation_job_id") == candidate.get("simulation_job_id")
        )
