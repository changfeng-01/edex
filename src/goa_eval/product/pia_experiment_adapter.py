from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from goa_eval.pia_ca_llso import DATA_SOURCE, ENGINEERING_VALIDITY
from goa_eval.pia_ca_llso.evolution import load_resume_state, run_evolution_loop
from goa_eval.product.artifact_store import ArtifactAlreadyExists, ArtifactIntegrityError, ArtifactRef
from goa_eval.product.models import (
    AuditEventRecord,
    CandidateRecord,
    ExperimentStatus,
    OptimizationExperimentRecord,
    SimulationJobRecord,
    SimulationJobStatus,
)
from goa_eval.product.state_machine import transition_experiment


EvolutionRunner = Callable[..., dict[str, Any]]
ResumeLoader = Callable[[str | Path, int], dict[str, Any]]


@dataclass(frozen=True)
class PiaExperimentMapping:
    experiment: OptimizationExperimentRecord
    candidates: tuple[CandidateRecord, ...]
    jobs: tuple[SimulationJobRecord, ...]
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True)
class _GenerationInput:
    generation: int
    rows: tuple[dict[str, Any], ...]
    status: str


class PiaExperimentAdapter:
    """Map native PIA evolution artifacts into product records without rewriting them."""

    def __init__(
        self,
        repository: Any,
        artifact_store: Any,
        *,
        runner: EvolutionRunner = run_evolution_loop,
        resume_loader: ResumeLoader = load_resume_state,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._runner = runner
        self._resume_loader = resume_loader

    def run(
        self,
        experiment_id: str,
        *,
        history: pd.DataFrame,
        candidates: pd.DataFrame,
        config: Mapping[str, Any],
        output_dir: str | Path,
        **kwargs: Any,
    ) -> PiaExperimentMapping:
        output = Path(output_dir)
        self._runner(history, candidates, config, output, **kwargs)
        parameter_columns = tuple(str(value) for value in config.get("parameter_columns", ()))
        if not parameter_columns:
            raise ValueError("PIA config requires parameter_columns for product mapping")
        return self.map_output(experiment_id, output, parameter_columns=parameter_columns)

    def load_resume_state(self, output_dir: str | Path, generation: int) -> dict[str, Any]:
        return self._resume_loader(output_dir, generation)

    def map_output(
        self,
        experiment_id: str,
        output_dir: str | Path,
        *,
        parameter_columns: Sequence[str],
    ) -> PiaExperimentMapping:
        experiment = self._repository.get_experiment(experiment_id)
        if experiment is None:
            raise KeyError(experiment_id)
        output = Path(output_dir).resolve()
        if not output.is_dir() or output.is_symlink():
            raise ValueError(f"PIA output is not a regular directory: {output}")
        parameters = tuple(str(column) for column in parameter_columns)
        if not parameters:
            raise ValueError("parameter_columns cannot be empty")

        generations = self._validate_output(output, parameters)
        if not generations:
            raise ValueError("PIA output contains no generation directories")

        events = self._repository.list_audit_events("experiment", experiment_id)
        mapped_snapshots = {
            (int(event.details["generation"]), str(event.details.get("snapshot_id", "")))
            for event in events
            if event.action == "pia.generation.mapped" and "generation" in event.details
        }
        product_candidates: list[CandidateRecord] = []
        new_candidates: list[CandidateRecord] = []
        generation_candidates: dict[int, list[CandidateRecord]] = {}
        for generation in generations:
            generation_candidates[generation.generation] = []
            for row in generation.rows:
                candidate = self._candidate_from_row(experiment, generation.generation, row, parameters)
                existing = self._repository.get_candidate(candidate.candidate_id)
                if existing is None:
                    existing = candidate
                    new_candidates.append(candidate)
                elif existing.experiment_id != experiment_id or existing.parameter_changes != candidate.parameter_changes:
                    raise ValueError(f"PIA candidate identity collision: {candidate.candidate_id}")
                product_candidates.append(existing)
                generation_candidates[generation.generation].append(existing)

        artifact_files = self._validated_artifact_files(output)
        snapshot_id = self._snapshot_id(output, artifact_files)
        artifacts = tuple(self._publish_files(experiment_id, output, artifact_files, snapshot_id))
        jobs_list: list[SimulationJobRecord] = []
        product_artifacts: list[ArtifactRef] = []
        for generation in generations:
            job, result_manifest_ref = self._job_for_generation(
                experiment,
                generation,
                generation_candidates[generation.generation],
                artifacts,
            )
            jobs_list.append(job)
            if result_manifest_ref is not None:
                product_artifacts.append(result_manifest_ref)
        jobs = tuple(jobs_list)
        artifacts = (*artifacts, *product_artifacts)
        for job in jobs:
            existing_job = self._repository.get_simulation_job(job.simulation_job_id)
            if existing_job is not None and (
                existing_job.project_id != job.project_id
                or existing_job.candidate_ids != job.candidate_ids
                or existing_job.adapter_type != job.adapter_type
            ):
                raise ValueError(f"PIA simulation job identity collision: {job.simulation_job_id}")
        metadata = self._mapping_metadata(generations, artifacts, output, snapshot_id)
        config = dict(experiment.strategy_config)
        config["pia_evolution"] = metadata
        desired_state = self._desired_experiment_state(generations, output)
        state = experiment.state
        if state != desired_state:
            if state in {ExperimentStatus.READY, ExperimentStatus.WAITING_FOR_SIMULATION}:
                state = transition_experiment(state, ExperimentStatus.RUNNING)
            if state == ExperimentStatus.RUNNING:
                state = transition_experiment(state, desired_state)
        if state != desired_state:
            raise ValueError(f"experiment cannot accept PIA output from state {state.value}")
        updated = replace(experiment, strategy_config=config, state=state)

        artifact_uris = [ref.uri for ref in artifacts]
        new_events: list[AuditEventRecord] = []
        for generation in generations:
            if (generation.generation, snapshot_id) in mapped_snapshots:
                continue
            generation_marker = f"generation_{generation.generation:03d}/"
            generation_refs = [uri for uri in artifact_uris if generation_marker in uri]
            event_identity = hashlib.sha256(
                f"pia-generation:{experiment_id}:{generation.generation}:{snapshot_id}".encode("utf-8")
            ).hexdigest()[:32]
            new_events.append(
                AuditEventRecord(
                    event_id=f"event_{event_identity}",
                    actor_id="system",
                    action="pia.generation.mapped",
                    subject_type="experiment",
                    subject_id=experiment_id,
                    details={
                        "generation": generation.generation,
                        "snapshot_id": snapshot_id,
                        "state": desired_state.value,
                        "candidate_count": len(generation.rows),
                        "simulation_job_id": next(
                            job.simulation_job_id
                            for job in jobs
                            if job.candidate_ids
                            == tuple(candidate.candidate_id for candidate in generation_candidates[generation.generation])
                        ),
                        "artifact_refs": generation_refs,
                    },
                )
            )
        self._repository.apply_pia_mapping(new_candidates, jobs, updated, new_events)
        persisted_jobs = tuple(
            self._repository.get_simulation_job(job.simulation_job_id) or job for job in jobs
        )
        return PiaExperimentMapping(updated, tuple(product_candidates), persisted_jobs, artifacts)

    def _job_for_generation(
        self,
        experiment: OptimizationExperimentRecord,
        generation: _GenerationInput,
        candidates: Sequence[CandidateRecord],
        artifacts: Sequence[ArtifactRef],
    ) -> tuple[SimulationJobRecord, ArtifactRef | None]:
        marker = f"generation_{generation.generation:03d}/"
        manifest_ref = next(
            ref for ref in artifacts if marker in ref.key and ref.key.endswith("/simulation_manifest.json")
        )
        batch_ref = next(ref for ref in artifacts if marker in ref.key and ref.key.endswith("/simulation_batch.csv"))
        identity = hashlib.sha256(
            f"pia-job:{experiment.experiment_id}:{generation.generation}".encode("utf-8")
        ).hexdigest()[:32]
        status = {
            "pending_simulation": SimulationJobStatus.WAITING_FOR_RESULTS,
            "results_imported": SimulationJobStatus.COMPLETED,
            "error": SimulationJobStatus.FAILED,
        }[generation.status]
        result_ref = None
        result_manifest_ref = None
        if status == SimulationJobStatus.COMPLETED:
            result_ref = next(
                (ref for ref in artifacts if marker in ref.key and ref.key.endswith("/imported_results.csv")),
                None,
            )
            if result_ref is None:
                raise ValueError(f"completed PIA generation is missing imported_results.csv: {generation.generation}")
            imported = pd.read_csv(self._artifact_store.resolve(result_ref))
            source_ids = {str(row["candidate_id"]) for row in generation.rows}
            if imported.empty or set(imported["candidate_id"].astype(str)) != source_ids:
                raise ValueError(
                    f"completed PIA generation results do not match selected candidates: {generation.generation}"
                )
            result_manifest = {
                "schema_version": "1.0",
                "simulation_job_id": f"job_{identity}",
                "generation": generation.generation,
                "candidate_ids": [candidate.candidate_id for candidate in candidates],
                "source_candidate_ids": sorted(source_ids),
                "result_ref": result_ref.uri,
                "result_sha256": result_ref.sha256,
                "data_source": DATA_SOURCE,
                "engineering_validity": ENGINEERING_VALIDITY,
                "must_resimulate": False,
            }
            key = manifest_ref.key.removesuffix("simulation_manifest.json") + "product_result_manifest.json"
            payload = (json.dumps(result_manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            try:
                result_manifest_ref = self._artifact_store.put_bytes(key, payload)
            except ArtifactAlreadyExists:
                result_manifest_ref = self._artifact_store.ref_from_uri(
                    f"artifact://{key}",
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )
        job = SimulationJobRecord(
            simulation_job_id=f"job_{identity}",
            project_id=experiment.project_id,
            candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
            adapter_type="pia_evolution",
            status=status,
            input_manifest_ref=manifest_ref.uri,
            result_manifest_ref=result_manifest_ref.uri if result_manifest_ref is not None else None,
            export_attempt=generation.generation + 1,
            batch_ref=batch_ref,
            result_ref=result_ref,
            result_sha256=result_ref.sha256 if result_ref is not None else None,
            error_code="PIA_SIMULATION_ERROR" if status == SimulationJobStatus.FAILED else None,
            retryable=status == SimulationJobStatus.FAILED,
        )
        return job, result_manifest_ref

    def _validate_output(self, output: Path, parameters: tuple[str, ...]) -> list[_GenerationInput]:
        generations: list[_GenerationInput] = []
        for directory in sorted(
            entry
            for entry in output.iterdir()
            if entry.name.startswith("generation_") and entry.name.removeprefix("generation_").isdigit()
        ):
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError(f"invalid PIA generation directory: {directory}")
            try:
                generation = int(directory.name.removeprefix("generation_"))
            except ValueError as exc:
                raise ValueError(f"invalid PIA generation directory: {directory.name}") from exc
            selected_path = directory / "pia_selected_candidates.csv"
            manifest_path = directory / "simulation_manifest.json"
            if not selected_path.is_file() or selected_path.is_symlink():
                raise ValueError(f"missing PIA selected candidates: {selected_path}")
            if not manifest_path.is_file() or manifest_path.is_symlink():
                raise ValueError(f"missing PIA simulation manifest: {manifest_path}")
            selected = pd.read_csv(selected_path)
            required = {"candidate_id", *parameters, "data_source", "engineering_validity", "must_resimulate"}
            missing = sorted(required.difference(selected.columns))
            if missing:
                raise ValueError(f"PIA selected candidates missing columns: {missing}")
            self._validate_boundary_frame(selected, selected_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self._validate_boundary_mapping(manifest, manifest_path)
            if int(manifest.get("generation", -1)) != generation:
                raise ValueError(f"PIA manifest generation mismatch: {manifest_path}")
            if int(manifest.get("candidate_count", -1)) != len(selected):
                raise ValueError(f"PIA manifest candidate_count mismatch: {manifest_path}")
            summary_path = directory / "generation_summary.json"
            if not summary_path.is_file() or summary_path.is_symlink():
                raise ValueError(f"missing PIA generation summary: {summary_path}")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self._validate_present_boundaries(summary, summary_path)
            status_value = summary.get("status", {})
            status = str(status_value.get("status", "")) if isinstance(status_value, dict) else str(status_value)
            if not status:
                raise ValueError(f"PIA generation status is missing: {summary_path}")
            if status not in {"pending_simulation", "results_imported", "error"}:
                raise ValueError(f"unsupported PIA generation status {status!r}: {summary_path}")
            rows = tuple(selected.to_dict(orient="records"))
            source_ids = [str(row["candidate_id"]) for row in rows]
            if len(source_ids) != len(set(source_ids)):
                raise ValueError(f"PIA generation contains duplicate candidate_id values: {selected_path}")
            generations.append(_GenerationInput(generation, rows, status))
        return generations

    @staticmethod
    def _validate_boundary_frame(frame: pd.DataFrame, source: Path) -> None:
        if not frame["data_source"].eq(DATA_SOURCE).all():
            raise ValueError(f"data_source must remain {DATA_SOURCE}: {source}")
        if not frame["engineering_validity"].eq(ENGINEERING_VALIDITY).all():
            raise ValueError(f"engineering_validity must remain {ENGINEERING_VALIDITY}: {source}")
        if not frame["must_resimulate"].map(_strict_true).all():
            raise ValueError(f"must_resimulate must remain true: {source}")

    @staticmethod
    def _validate_boundary_mapping(value: Mapping[str, Any], source: Path) -> None:
        if value.get("data_source") != DATA_SOURCE:
            raise ValueError(f"data_source must remain {DATA_SOURCE}: {source}")
        if value.get("engineering_validity") != ENGINEERING_VALIDITY:
            raise ValueError(f"engineering_validity must remain {ENGINEERING_VALIDITY}: {source}")
        if value.get("must_resimulate") is not True:
            raise ValueError(f"must_resimulate must remain true: {source}")

    @staticmethod
    def _validate_present_boundaries(value: Any, source: Path) -> None:
        if isinstance(value, dict):
            if "data_source" in value and value["data_source"] != DATA_SOURCE:
                raise ValueError(f"data_source must remain {DATA_SOURCE}: {source}")
            if "engineering_validity" in value and value["engineering_validity"] != ENGINEERING_VALIDITY:
                raise ValueError(f"engineering_validity must remain {ENGINEERING_VALIDITY}: {source}")
            if "must_resimulate" in value and _boundary_bool(value["must_resimulate"]) is None:
                raise ValueError(f"must_resimulate must remain a boolean boundary: {source}")
            for nested in value.values():
                PiaExperimentAdapter._validate_present_boundaries(nested, source)
        elif isinstance(value, list):
            for nested in value:
                PiaExperimentAdapter._validate_present_boundaries(nested, source)

    @staticmethod
    def _candidate_from_row(
        experiment: OptimizationExperimentRecord,
        generation: int,
        row: Mapping[str, Any],
        parameters: tuple[str, ...],
    ) -> CandidateRecord:
        source_id = str(row["candidate_id"])
        identity = hashlib.sha256(f"{experiment.experiment_id}:{generation}:{source_id}".encode()).hexdigest()[:32]
        changes = {column: _json_scalar(row[column], column) for column in parameters}
        score = row.get("selection_score")
        selection_score = None if score is None or pd.isna(score) else float(score)
        return CandidateRecord(
            candidate_id=f"candidate_{identity}",
            experiment_id=experiment.experiment_id,
            parent_design_version_id=experiment.baseline_design_version_id,
            parameter_changes=changes,
            strategy="pia",
            reason_codes=(f"pia_generation:{generation}", f"pia_source:{source_id}"),
            selection_score=selection_score,
            must_resimulate=True,
        )

    def _publish_files(
        self,
        experiment_id: str,
        output: Path,
        files: Sequence[Path],
        snapshot_id: str,
    ) -> list[ArtifactRef]:
        refs: list[ArtifactRef] = []
        prefix = f"phase3/experiments/{experiment_id}/pia/snapshots/{snapshot_id}"
        for source in files:
            relative = source.relative_to(output).as_posix()
            key = f"{prefix}/{relative}"
            digest = _sha256(source)
            try:
                ref = self._artifact_store.put_file(key, source)
            except ArtifactAlreadyExists:
                ref = self._artifact_store.ref_from_uri(f"artifact://{key}", expected_sha256=digest)
            if ref.sha256 != digest:
                raise ArtifactIntegrityError(f"published PIA artifact differs from source: {key}")
            refs.append(ref)
        return refs

    @staticmethod
    def _snapshot_id(output: Path, files: Sequence[Path]) -> str:
        digest = hashlib.sha256()
        for source in files:
            digest.update(source.relative_to(output).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(_sha256(source).encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _validated_artifact_files(self, output: Path) -> tuple[Path, ...]:
        root_names = {
            "generation_state.jsonl",
            "evolution_history.csv",
            "evolution_summary.json",
            "evolution_report.md",
        }
        generation_names = {
            "offspring_candidates.csv",
            "pia_selected_candidates.csv",
            "simulation_batch.csv",
            "simulation_manifest.json",
            "generation_summary.json",
            "simulator_invocation.json",
            "simulator_stdout.txt",
            "simulator_stderr.txt",
            "simulation_results.csv",
            "imported_results.csv",
        }
        selected: list[Path] = []
        for source in sorted(output.rglob("*")):
            if source.is_symlink():
                raise ValueError(f"PIA output cannot contain symlinks: {source}")
            if not source.is_file():
                continue
            relative = source.relative_to(output)
            allowed = (
                len(relative.parts) == 1 and relative.name in root_names
            ) or (
                len(relative.parts) == 2
                and relative.parts[0].startswith("generation_")
                and relative.name in generation_names
            )
            if not allowed:
                continue
            if source.suffix == ".json":
                self._validate_present_boundaries(json.loads(source.read_text(encoding="utf-8")), source)
            elif source.suffix == ".jsonl":
                for line in source.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        self._validate_present_boundaries(json.loads(line), source)
            elif source.suffix == ".csv":
                frame = pd.read_csv(source)
                is_result = source.name in {"simulation_results.csv", "imported_results.csv"}
                if is_result and "must_resimulate" in frame.columns:
                    if not frame["must_resimulate"].map(lambda value: _boundary_bool(value) is False).all():
                        raise ValueError(f"imported results must set must_resimulate to false: {source}")
                    if "data_source" in frame.columns and not frame["data_source"].eq(DATA_SOURCE).all():
                        raise ValueError(f"data_source must remain {DATA_SOURCE}: {source}")
                    if "engineering_validity" in frame.columns and not frame["engineering_validity"].eq(
                        ENGINEERING_VALIDITY
                    ).all():
                        raise ValueError(f"engineering_validity must remain {ENGINEERING_VALIDITY}: {source}")
                elif {"data_source", "engineering_validity", "must_resimulate"} <= set(frame.columns):
                    self._validate_boundary_frame(frame, source)
                elif "data_source" in frame.columns and not frame["data_source"].eq(DATA_SOURCE).all():
                    raise ValueError(f"data_source must remain {DATA_SOURCE}: {source}")
                elif "engineering_validity" in frame.columns and not frame["engineering_validity"].eq(
                    ENGINEERING_VALIDITY
                ).all():
                    raise ValueError(f"engineering_validity must remain {ENGINEERING_VALIDITY}: {source}")
            selected.append(source)
        return tuple(selected)

    @staticmethod
    def _desired_experiment_state(
        generations: Sequence[_GenerationInput],
        output: Path,
    ) -> ExperimentStatus:
        summary_path = output / "evolution_summary.json"
        stop_reason = None
        if summary_path.is_file() and not summary_path.is_symlink():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            stop_reason = summary.get("stop_reason")
        if generations[-1].status == "error":
            return ExperimentStatus.FAILED
        if generations[-1].status == "pending_simulation" or stop_reason == "pending_simulation_results":
            return ExperimentStatus.WAITING_FOR_SIMULATION
        return ExperimentStatus.COMPLETED

    @staticmethod
    def _mapping_metadata(
        generations: Sequence[_GenerationInput],
        artifacts: Sequence[ArtifactRef],
        output: Path,
        snapshot_id: str,
    ) -> dict[str, Any]:
        stop_reason = None
        summary_path = output / "evolution_summary.json"
        if summary_path.is_file() and not summary_path.is_symlink():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            stop_reason = summary.get("stop_reason")
        return {
            "snapshot_id": snapshot_id,
            "latest_generation": max(item.generation for item in generations),
            "stop_reason": stop_reason,
            "generations": [
                {
                    "generation": item.generation,
                    "candidate_count": len(item.rows),
                    "artifact_refs": [
                        ref.uri for ref in artifacts if f"generation_{item.generation:03d}/" in ref.key
                    ],
                }
                for item in generations
            ],
        }


def _strict_true(value: Any) -> bool:
    return value is True or value == 1 or (isinstance(value, str) and value.strip().lower() == "true")


def _boundary_bool(value: Any) -> bool | None:
    if value is True or value == 1 or (isinstance(value, str) and value.strip().lower() == "true"):
        return True
    if value is False or value == 0 or (isinstance(value, str) and value.strip().lower() == "false"):
        return False
    return None


def _json_scalar(value: Any, column: str) -> Any:
    if pd.isna(value):
        raise ValueError(f"PIA parameter {column} cannot be null")
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"PIA parameter {column} must be finite")
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"PIA parameter {column} must be a JSON scalar")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
