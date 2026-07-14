from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from goa_eval.pia_ca_llso.simulation_contract import build_simulation_batch, import_simulation_results
from goa_eval.product.artifact_store import ArtifactAlreadyExists, ArtifactRef
from goa_eval.product.models import (
    AuditEventRecord,
    CandidateRecord,
    CandidateStatus,
    SimulationJobRecord,
    SimulationJobStatus,
    new_id,
)
from goa_eval.product.state_machine import transition_candidate, transition_simulation_job


class SimulationJobConflict(ValueError):
    pass


class SimulationImportError(ValueError):
    pass


@dataclass(frozen=True)
class SimulationImportPreview:
    simulation_job_id: str
    manifest_sha256: str
    result_sha256: str
    quarantined_ref: ArtifactRef
    validated_ref: ArtifactRef
    row_count: int
    warnings: tuple[dict[str, Any], ...] = ()


class SimulationJobService:
    def __init__(self, repository: Any, artifact_store: Any, project_service: Any) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._project_service = project_service

    def create_manual_job(
        self,
        candidate_ids: Iterable[str],
        adapter_type: str = "manual",
    ) -> SimulationJobRecord:
        ids = tuple(dict.fromkeys(str(value) for value in candidate_ids))
        if not ids:
            raise SimulationJobConflict("at least one approved candidate is required")
        if adapter_type != "manual":
            raise SimulationJobConflict("Phase 2 only supports the manual adapter")
        candidates = [self._require_candidate(candidate_id) for candidate_id in ids]
        if any(candidate.status != CandidateStatus.APPROVED for candidate in candidates):
            raise SimulationJobConflict("all candidates must be explicitly approved")
        experiments = [self._repository.get_experiment(candidate.experiment_id) for candidate in candidates]
        if any(experiment is None for experiment in experiments):
            raise SimulationJobConflict("candidate experiment was not found")
        project_ids = {experiment.project_id for experiment in experiments}
        if len(project_ids) != 1:
            raise SimulationJobConflict("all candidates must belong to the same project")
        job = SimulationJobRecord(
            simulation_job_id=new_id("job"),
            project_id=project_ids.pop(),
            candidate_ids=ids,
            adapter_type="manual",
        )
        self._repository.add_simulation_job(job)
        self._audit(job, "simulation_job.created", {"candidate_ids": list(ids)})
        return job

    def export_job(self, job_id: str, force_new_attempt: bool = False) -> SimulationJobRecord:
        job = self._require_job(job_id)
        if job.batch_ref is not None and not force_new_attempt:
            return job
        if job.status not in {SimulationJobStatus.DRAFT, SimulationJobStatus.WAITING_FOR_RESULTS}:
            raise SimulationJobConflict(f"job cannot be exported from {job.status.value}")
        candidates = [self._require_candidate(candidate_id) for candidate_id in job.candidate_ids]
        if any(candidate.status not in {CandidateStatus.APPROVED, CandidateStatus.SIMULATION_PENDING} for candidate in candidates):
            raise SimulationJobConflict("only approved candidates can be exported")
        selected = self._candidate_frame(candidates)
        generation = job.export_attempt + 1
        config = self._simulation_config(selected)
        batch, manifest = build_simulation_batch(selected, config, generation)
        batch["parameter_hash"] = [self._parameter_hash(candidate.parameter_changes) for candidate in candidates]
        prefix = f"phase2/simulation_jobs/{job.simulation_job_id}/exports/{generation}"
        batch_ref = self._artifact_store.put_bytes(
            f"{prefix}/simulation_batch.csv",
            batch.to_csv(index=False).encode("utf-8"),
        )
        manifest.update(
            {
                "simulation_job_id": job.simulation_job_id,
                "adapter_type": "manual",
                "batch_ref": batch_ref.uri,
                "batch_sha256": batch_ref.sha256,
                "parameter_columns": list(config["parameter_columns"]),
            }
        )
        manifest_ref = self._artifact_store.put_bytes(
            f"{prefix}/simulation_manifest.json",
            self._json_bytes(manifest),
        )
        exported_status = (
            transition_simulation_job(job.status, SimulationJobStatus.EXPORTED)
            if job.status == SimulationJobStatus.DRAFT
            else job.status
        )
        if exported_status == SimulationJobStatus.EXPORTED:
            exported_status = transition_simulation_job(exported_status, SimulationJobStatus.WAITING_FOR_RESULTS)
        updated = replace(
            job,
            status=exported_status,
            input_manifest_ref=manifest_ref.uri,
            export_attempt=generation,
            attempt=job.attempt + 1,
            batch_ref=batch_ref,
            error_code=None,
            retryable=False,
        )
        self._repository.update_simulation_job(updated)
        for candidate in candidates:
            if candidate.status == CandidateStatus.APPROVED:
                self._repository.update_candidate(
                    replace(
                        candidate,
                        status=transition_candidate(candidate.status, CandidateStatus.SIMULATION_PENDING),
                        simulation_job_id=job.simulation_job_id,
                    )
                )
        self._audit(updated, "simulation_job.exported", {"batch_ref": batch_ref.uri})
        return updated

    def preview_import(self, job_id: str, result_path: Path) -> SimulationImportPreview:
        job = self._require_job(job_id)
        source = Path(result_path)
        if ".." in source.parts or not source.is_file() or source.is_symlink():
            raise SimulationImportError("result path must be a regular file without traversal")
        raw = source.read_bytes()
        result_sha = hashlib.sha256(raw).hexdigest()
        if job.status == SimulationJobStatus.COMPLETED:
            if job.result_sha256 != result_sha:
                raise SimulationImportError("different result bytes cannot replace a committed import")
            return self._load_preview(job)
        if job.status != SimulationJobStatus.WAITING_FOR_RESULTS or job.batch_ref is None:
            raise SimulationJobConflict(f"job cannot import results from {job.status.value}")
        attempt = job.import_attempt + 1
        prefix = f"phase2/simulation_jobs/{job.simulation_job_id}/imports/{attempt}/{result_sha}"
        quarantined_ref = self._put_once(f"{prefix}/quarantine.csv", raw)
        try:
            batch = pd.read_csv(self._artifact_store.resolve(job.batch_ref))
            raw_frame = pd.read_csv(source)
            self._validate_parameter_hashes(raw_frame, batch)
            config = self._simulation_config(batch)
            validated = import_simulation_results(source, batch, config, generation=job.export_attempt)
            if set(validated["candidate_id"].astype(str)) != set(job.candidate_ids):
                raise ValueError("partial result imports require an explicit partial policy")
            validated_ref = self._artifact_store.put_bytes(
                f"{prefix}/validated.csv",
                validated.to_csv(index=False).encode("utf-8"),
            )
            report = validated.attrs.get("validation_report", {})
            preview_manifest = {
                "simulation_job_id": job.simulation_job_id,
                "candidate_ids": list(job.candidate_ids),
                "result_sha256": result_sha,
                "quarantined_ref": quarantined_ref.uri,
                "validated_ref": validated_ref.uri,
                "validated_sha256": validated_ref.sha256,
                "row_count": len(validated),
                "warnings": report.get("warnings", []),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
            preview_manifest_ref = self._artifact_store.put_bytes(
                f"{prefix}/preview_manifest.json",
                self._json_bytes(preview_manifest),
            )
            updated = replace(
                job,
                status=SimulationJobStatus.VALIDATING,
                import_attempt=attempt,
                command_manifest_ref=preview_manifest_ref.uri,
                result_ref=validated_ref,
                result_sha256=result_sha,
                error_code=None,
                retryable=False,
            )
            self._repository.update_simulation_job(updated)
            self._audit(updated, "simulation_job.import_previewed", {"result_sha256": result_sha})
            return SimulationImportPreview(
                simulation_job_id=job.simulation_job_id,
                manifest_sha256=preview_manifest_ref.sha256,
                result_sha256=result_sha,
                quarantined_ref=quarantined_ref,
                validated_ref=validated_ref,
                row_count=len(validated),
                warnings=tuple(report.get("warnings", [])),
            )
        except Exception as exc:
            failed = replace(
                job,
                status=SimulationJobStatus.FAILED,
                import_attempt=attempt,
                result_ref=quarantined_ref,
                result_sha256=result_sha,
                error_code="RESULT_CONTRACT_INVALID",
                retryable=True,
            )
            self._repository.update_simulation_job(failed)
            self._audit(failed, "simulation_job.import_failed", {"error": str(exc)})
            raise SimulationImportError(str(exc)) from exc

    def commit_import(self, job_id: str, manifest_sha256: str) -> SimulationJobRecord:
        job = self._require_job(job_id)
        if job.status == SimulationJobStatus.COMPLETED:
            self._verify_preview_manifest(job, manifest_sha256)
            return job
        if job.status != SimulationJobStatus.VALIDATING or job.result_ref is None:
            raise SimulationJobConflict("job has no validated import preview")
        preview = self._verify_preview_manifest(job, manifest_sha256)
        validated = pd.read_csv(self._artifact_store.resolve(job.result_ref))
        accepted_ref = self._artifact_store.put_bytes(
            f"phase2/simulation_jobs/{job.simulation_job_id}/accepted/{job.result_sha256}/results.csv",
            validated.to_csv(index=False).encode("utf-8"),
        )
        result_versions: dict[str, str] = {}
        for candidate_id in job.candidate_ids:
            candidate = self._require_candidate(candidate_id)
            version = self._project_service.create_design_version(
                job.project_id,
                f"simulation result {candidate_id}",
                parameter_set_ref=accepted_ref.uri,
                parent_version_id=candidate.parent_design_version_id,
                source_candidate_id=candidate_id,
                actor_id="simulation_import",
            )
            result_versions[candidate_id] = version.design_version_id
            self._repository.update_candidate(
                replace(
                    candidate,
                    status=transition_candidate(candidate.status, CandidateStatus.RESIMULATED),
                    result_design_version_id=version.design_version_id,
                )
            )
        provenance = {
            "candidate_ids": list(job.candidate_ids),
            "candidate_id": job.candidate_ids[0] if len(job.candidate_ids) == 1 else None,
            "simulation_job_id": job.simulation_job_id,
            "result_sha256": job.result_sha256,
            "accepted_results_ref": accepted_ref.uri,
            "result_design_versions": result_versions,
            "preview_manifest_sha256": manifest_sha256,
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        }
        provenance_ref = self._artifact_store.put_bytes(
            f"phase2/simulation_jobs/{job.simulation_job_id}/accepted/{job.result_sha256}/provenance.json",
            self._json_bytes(provenance),
        )
        completed = replace(
            job,
            status=transition_simulation_job(job.status, SimulationJobStatus.COMPLETED),
            result_manifest_ref=provenance_ref.uri,
            result_ref=provenance_ref,
            error_code=None,
            retryable=False,
        )
        self._repository.update_simulation_job(completed)
        self._audit(completed, "simulation_job.import_committed", {"result_ref": provenance_ref.uri})
        return completed

    def retry_job(self, job_id: str) -> SimulationJobRecord:
        job = self._require_job(job_id)
        if job.status != SimulationJobStatus.FAILED or not job.retryable:
            raise SimulationJobConflict("only retryable failed jobs can be retried")
        updated = replace(
            job,
            status=transition_simulation_job(job.status, SimulationJobStatus.WAITING_FOR_RESULTS),
            import_attempt=job.import_attempt + 1,
            error_code=None,
            retryable=False,
        )
        self._repository.update_simulation_job(updated)
        self._audit(updated, "simulation_job.retried", {"import_attempt": updated.import_attempt})
        return updated

    def _verify_preview_manifest(self, job: SimulationJobRecord, sha256: str) -> dict[str, Any]:
        if not job.command_manifest_ref:
            raise SimulationImportError("preview manifest is missing")
        ref = self._artifact_store.ref_from_uri(job.command_manifest_ref, sha256)
        preview = json.loads(self._artifact_store.resolve(ref).read_text(encoding="utf-8"))
        if preview.get("simulation_job_id") != job.simulation_job_id:
            raise SimulationImportError("preview manifest belongs to another job")
        if preview.get("result_sha256") != job.result_sha256:
            raise SimulationImportError("preview manifest result checksum does not match")
        return preview

    def _load_preview(self, job: SimulationJobRecord) -> SimulationImportPreview:
        if not job.command_manifest_ref:
            raise SimulationImportError("preview manifest is missing")
        ref = self._artifact_store.ref_from_uri(job.command_manifest_ref)
        payload = json.loads(self._artifact_store.resolve(ref).read_text(encoding="utf-8"))
        quarantine = self._artifact_store.ref_from_uri(payload["quarantined_ref"])
        validated = self._artifact_store.ref_from_uri(payload["validated_ref"], payload["validated_sha256"])
        return SimulationImportPreview(
            job.simulation_job_id,
            ref.sha256,
            str(payload["result_sha256"]),
            quarantine,
            validated,
            int(payload["row_count"]),
            tuple(payload.get("warnings", [])),
        )

    def _require_job(self, job_id: str) -> SimulationJobRecord:
        job = self._repository.get_simulation_job(job_id)
        if job is None:
            raise SimulationJobConflict(f"simulation job was not found: {job_id}")
        return job

    def _require_candidate(self, candidate_id: str) -> CandidateRecord:
        candidate = self._repository.get_candidate(candidate_id)
        if candidate is None:
            raise SimulationJobConflict(f"candidate was not found: {candidate_id}")
        return candidate

    def _audit(self, job: SimulationJobRecord, action: str, details: dict[str, Any]) -> None:
        self._repository.append_audit_event(
            AuditEventRecord(new_id("event"), "system", action, "simulation_job", job.simulation_job_id, details)
        )

    @staticmethod
    def _candidate_frame(candidates: list[CandidateRecord]) -> pd.DataFrame:
        rows = []
        for rank, candidate in enumerate(candidates, start=1):
            rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    **candidate.parameter_changes,
                    "selected_rank": rank,
                    "evidence_state": "pending_simulation",
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _simulation_config(frame: pd.DataFrame) -> dict[str, Any]:
        metadata = {
            "candidate_id",
            "selected_rank",
            "generation",
            "evidence_state",
            "must_resimulate",
            "data_source",
            "engineering_validity",
            "parameter_hash",
        }
        parameters = [column for column in frame.columns if column not in metadata]
        return {
            "parameter_columns": parameters,
            "simulation_executor": {
                "mode": "offline",
                "result_required_columns": [
                    "candidate_id",
                    "parameter_hash",
                    "overall_score",
                    "hard_constraint_passed",
                ],
            },
        }

    @staticmethod
    def _validate_parameter_hashes(results: pd.DataFrame, batch: pd.DataFrame) -> None:
        if "parameter_hash" not in results.columns:
            raise ValueError("missing required result column: parameter_hash")
        expected = batch.set_index(batch["candidate_id"].astype(str))["parameter_hash"].astype(str)
        for _, row in results.iterrows():
            candidate_id = str(row.get("candidate_id", ""))
            if candidate_id not in expected.index or str(row["parameter_hash"]) != expected[candidate_id]:
                raise ValueError(f"parameter hash mismatch for candidate_id: {candidate_id}")

    def _put_once(self, key: str, payload: bytes) -> ArtifactRef:
        try:
            return self._artifact_store.put_bytes(key, payload)
        except ArtifactAlreadyExists:
            return self._artifact_store.ref_from_uri(f"artifact://{key}", hashlib.sha256(payload).hexdigest())

    @staticmethod
    def _parameter_hash(changes: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(changes, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _json_bytes(payload: dict[str, Any]) -> bytes:
        return (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
