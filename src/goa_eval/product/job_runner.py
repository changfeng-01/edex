from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from goa_eval.product.models import (
    AuditEventRecord,
    CandidateStatus,
    SimulationJobRecord,
    SimulationJobStatus,
    new_id,
)
from goa_eval.product.state_machine import transition_candidate, transition_simulation_job


class JobExecutionDisabled(PermissionError):
    pass


@dataclass(frozen=True)
class ExecutionCommand:
    argv: tuple[str, ...] | Sequence[str]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    evidence: Mapping[str, Any] | None = None
    output_files: tuple[str, ...] | Sequence[str] = ()


@dataclass(frozen=True)
class JobRunResult:
    simulation_job_id: str
    attempt: int
    exit_code: int | None
    timed_out: bool
    logs_ref: str


class ProductJobRunner:
    """Execute queued jobs only through trusted, registered simulator adapters."""

    def __init__(self, repository: Any, artifact_store: Any, registry: Any, settings: Any) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._registry = registry
        self._settings = settings

    def run_job(self, job_id: str, *, timeout_seconds: float = 300) -> JobRunResult | None:
        if not self._settings.job_execution_enabled:
            raise JobExecutionDisabled("simulation job execution is disabled")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        job = self._repository.get_simulation_job(job_id)
        if job is None:
            raise KeyError(f"simulation job was not found: {job_id}")
        adapter = self._registry.get(job.adapter_type)
        claimed = self._repository.claim_simulation_job(job_id)
        if claimed is None:
            return None

        with TemporaryDirectory(prefix=f"circuitpilot-{job_id}-") as temporary:
            work_dir = Path(temporary).resolve()
            try:
                command = adapter.build_execution(claimed, self._artifact_store, work_dir)
                argv = self._validated_argv(command.argv)
                cwd = Path(command.cwd or work_dir).resolve()
                if not cwd.is_dir() or cwd.is_symlink():
                    raise ValueError(f"adapter working directory is invalid: {cwd}")
                environment = None
                if command.env is not None:
                    environment = {**os.environ, **{str(key): str(value) for key, value in command.env.items()}}
                completed = subprocess.run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=cwd,
                    env=environment,
                )
                result_manifest_ref = None
                if completed.returncode == 0:
                    try:
                        result_manifest_ref = self._persist_outputs(
                            claimed,
                            work_dir,
                            command.output_files,
                            dict(command.evidence or {}),
                        )
                    except FileNotFoundError as exc:
                        return self._finish(
                            claimed,
                            argv,
                            stdout=completed.stdout or "",
                            stderr=str(exc),
                            exit_code=completed.returncode,
                            timed_out=False,
                            evidence=dict(command.evidence or {}),
                            error_code_override="SIMULATION_OUTPUT_MISSING",
                        )
                return self._finish(
                    claimed,
                    argv,
                    stdout=completed.stdout or "",
                    stderr=completed.stderr or "",
                    exit_code=completed.returncode,
                    timed_out=False,
                    evidence=dict(command.evidence or {}),
                    result_manifest_ref=result_manifest_ref,
                )
            except subprocess.TimeoutExpired as exc:
                return self._finish(
                    claimed,
                    argv,
                    stdout=_timeout_text(exc.stdout),
                    stderr=_timeout_text(exc.stderr),
                    exit_code=None,
                    timed_out=True,
                    evidence=dict(command.evidence or {}),
                )
            except Exception as exc:
                return self._finish(
                    claimed,
                    (),
                    stdout="",
                    stderr=str(exc),
                    exit_code=None,
                    timed_out=False,
                    evidence={},
                    internal_error=True,
                )

    def _finish(
        self,
        job: SimulationJobRecord,
        argv: Sequence[str],
        *,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        timed_out: bool,
        evidence: Mapping[str, Any],
        internal_error: bool = False,
        error_code_override: str | None = None,
        result_manifest_ref: Any | None = None,
    ) -> JobRunResult:
        successful = (
            not timed_out
            and not internal_error
            and error_code_override is None
            and exit_code == 0
            and result_manifest_ref is not None
        )
        status = SimulationJobStatus.WAITING_FOR_RESULTS if successful else SimulationJobStatus.FAILED
        error_code = error_code_override
        if timed_out:
            error_code = "SIMULATION_TIMEOUT"
        elif internal_error:
            error_code = "SIMULATION_RUNNER_ERROR"
        elif not successful and error_code is None:
            error_code = "SIMULATION_PROCESS_FAILED"
        log = {
            "simulation_job_id": job.simulation_job_id,
            "adapter_type": job.adapter_type,
            "attempt": job.attempt,
            "argv": list(argv),
            "shell": False,
            "timeout": timed_out,
            "status": "waiting_for_results" if successful else "timeout" if timed_out else "failed",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "error_code": error_code,
            "evidence": dict(evidence),
            "result_manifest_ref": result_manifest_ref.uri if result_manifest_ref is not None else None,
        }
        log_ref = self._artifact_store.put_bytes(
            f"phase3/simulation_jobs/{job.simulation_job_id}/attempts/{job.attempt}/execution_log.json",
            (json.dumps(log, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
        )
        updated = replace(
            job,
            status=transition_simulation_job(job.status, status),
            logs_ref=log_ref.uri,
            result_manifest_ref=result_manifest_ref.uri if result_manifest_ref is not None else None,
            result_ref=result_manifest_ref,
            error_code=error_code,
            retryable=not successful,
        )
        candidate_updates = []
        if status == SimulationJobStatus.FAILED:
            for candidate_id in job.candidate_ids:
                candidate = self._repository.get_candidate(candidate_id)
                if candidate is not None and candidate.status == CandidateStatus.SIMULATION_PENDING:
                    candidate_updates.append(
                        replace(
                            candidate,
                            status=transition_candidate(candidate.status, CandidateStatus.SIMULATION_FAILED),
                        )
                    )
        event = AuditEventRecord(
            event_id=new_id("event"),
            actor_id="job_runner",
            action="simulation_job.execution_finished",
            subject_type="simulation_job",
            subject_id=job.simulation_job_id,
            details={
                "attempt": job.attempt,
                "status": status.value,
                "exit_code": exit_code,
                "error_code": error_code,
                "logs_ref": log_ref.uri,
            },
        )
        self._repository.apply_simulation_job_update(updated, candidate_updates, event)
        return JobRunResult(job.simulation_job_id, job.attempt, exit_code, timed_out, log_ref.uri)

    def _persist_outputs(
        self,
        job: SimulationJobRecord,
        work_dir: Path,
        output_files: Sequence[str],
        evidence: Mapping[str, Any],
    ) -> Any:
        refs = []
        for relative_name in output_files:
            relative = PurePosixPath(str(relative_name))
            if (
                relative.is_absolute()
                or "\\" in str(relative_name)
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ValueError(f"adapter declared an invalid output path: {relative_name!r}")
            source = work_dir.joinpath(*relative.parts).resolve()
            if work_dir not in source.parents or not source.is_file() or source.is_symlink():
                raise FileNotFoundError(f"declared simulator output is missing: {relative.as_posix()}")
            refs.append(
                self._artifact_store.put_file(
                    f"phase3/simulation_jobs/{job.simulation_job_id}/attempts/{job.attempt}/outputs/{relative.as_posix()}",
                    source,
                )
            )
        manifest = {
            "simulation_job_id": job.simulation_job_id,
            "adapter_type": job.adapter_type,
            "attempt": job.attempt,
            "outputs": [
                {"uri": ref.uri, "sha256": ref.sha256, "size_bytes": ref.size_bytes} for ref in refs
            ],
            "evidence": dict(evidence),
        }
        return self._artifact_store.put_bytes(
            f"phase3/simulation_jobs/{job.simulation_job_id}/attempts/{job.attempt}/result_manifest.json",
            (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
        )

    @staticmethod
    def _validated_argv(argv: Sequence[str]) -> tuple[str, ...]:
        values = tuple(str(value) for value in argv)
        if not values or not values[0].strip() or any("\x00" in value for value in values):
            raise ValueError("registered adapter returned invalid command arguments")
        return values


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
