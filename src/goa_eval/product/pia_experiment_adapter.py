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
    new_id,
)
from goa_eval.product.state_machine import transition_experiment


EvolutionRunner = Callable[..., dict[str, Any]]
ResumeLoader = Callable[[str | Path, int], dict[str, Any]]


@dataclass(frozen=True)
class PiaExperimentMapping:
    experiment: OptimizationExperimentRecord
    candidates: tuple[CandidateRecord, ...]
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True)
class _GenerationInput:
    generation: int
    rows: tuple[dict[str, Any], ...]


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
        mapped_generations = {
            int(event.details["generation"])
            for event in events
            if event.action == "pia.generation.mapped" and "generation" in event.details
        }
        product_candidates: list[CandidateRecord] = []
        for generation in generations:
            for row in generation.rows:
                candidate = self._candidate_from_row(experiment, generation.generation, row, parameters)
                existing = self._repository.get_candidate(candidate.candidate_id)
                if existing is None:
                    self._repository.add_candidate(candidate)
                    existing = candidate
                elif existing.experiment_id != experiment_id or existing.parameter_changes != candidate.parameter_changes:
                    raise ValueError(f"PIA candidate identity collision: {candidate.candidate_id}")
                product_candidates.append(existing)

        artifacts = tuple(self._publish_files(experiment_id, output))
        metadata = self._mapping_metadata(generations, artifacts, output)
        config = dict(experiment.strategy_config)
        config["pia_evolution"] = metadata
        state = experiment.state
        if state == ExperimentStatus.READY:
            state = transition_experiment(state, ExperimentStatus.RUNNING)
        if state == ExperimentStatus.RUNNING:
            state = transition_experiment(state, ExperimentStatus.WAITING_FOR_SIMULATION)
        if state != ExperimentStatus.WAITING_FOR_SIMULATION:
            raise ValueError(f"experiment cannot accept pending PIA simulation work from state {state.value}")
        updated = replace(experiment, strategy_config=config, state=state)
        self._repository.update_experiment(updated)

        artifact_uris = [ref.uri for ref in artifacts]
        for generation in generations:
            if generation.generation in mapped_generations:
                continue
            generation_marker = f"generation_{generation.generation:03d}/"
            generation_refs = [uri for uri in artifact_uris if generation_marker in uri]
            self._repository.append_audit_event(
                AuditEventRecord(
                    event_id=new_id("event"),
                    actor_id="system",
                    action="pia.generation.mapped",
                    subject_type="experiment",
                    subject_id=experiment_id,
                    details={
                        "generation": generation.generation,
                        "state": ExperimentStatus.WAITING_FOR_SIMULATION.value,
                        "candidate_count": len(generation.rows),
                        "artifact_refs": generation_refs,
                    },
                )
            )
        return PiaExperimentMapping(updated, tuple(product_candidates), artifacts)

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
            rows = tuple(selected.to_dict(orient="records"))
            generations.append(_GenerationInput(generation, rows))
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

    def _publish_files(self, experiment_id: str, output: Path) -> list[ArtifactRef]:
        refs: list[ArtifactRef] = []
        prefix = f"phase3/experiments/{experiment_id}/pia"
        for source in sorted(output.rglob("*")):
            if source.is_symlink():
                raise ValueError(f"PIA output cannot contain symlinks: {source}")
            if not source.is_file():
                continue
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
    def _mapping_metadata(
        generations: Sequence[_GenerationInput],
        artifacts: Sequence[ArtifactRef],
        output: Path,
    ) -> dict[str, Any]:
        stop_reason = None
        summary_path = output / "evolution_summary.json"
        if summary_path.is_file() and not summary_path.is_symlink():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            stop_reason = summary.get("stop_reason")
        return {
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
