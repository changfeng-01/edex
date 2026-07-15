import json
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.product.artifact_store import LocalArtifactStore
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.models import ExperimentStatus, SimulationJobStatus
from goa_eval.product.pia_experiment_adapter import PiaExperimentAdapter
from goa_eval.product.project_service import ProjectService
from goa_eval.product.repositories import SqlAlchemyProductRepository


@pytest.fixture
def pia_product_context(tmp_path):
    repository = SqlAlchemyProductRepository(make_engine(f"sqlite:///{tmp_path / 'product.db'}"))
    create_schema(repository._sessions.kw["bind"])
    store = LocalArtifactStore(tmp_path / "artifacts")
    projects = ProjectService(repository, store)
    workspace = projects.create_workspace("PIA team")
    project = projects.create_project(workspace.workspace_id, "GOA", "goa_8k", "spec_v1").project
    baseline = projects.create_design_version(project.project_id, "baseline")
    experiment = ExperimentService(repository).create_experiment(
        project.project_id,
        baseline.design_version_id,
        {"strategy": "pia"},
    )
    return repository, store, experiment, tmp_path


def _write_pending_generation(root: Path) -> bytes:
    generation = root / "generation_000"
    generation.mkdir(parents=True)
    selected = pd.DataFrame(
        [
            {
                "candidate_id": "pia_source_a",
                "x1": 1.25,
                "x2": 4.5,
                "selection_score": 0.91,
                "must_resimulate": True,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            },
            {
                "candidate_id": "pia_source_b",
                "x1": 2.5,
                "x2": 3.0,
                "selection_score": 0.82,
                "must_resimulate": True,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            },
        ]
    )
    selected_path = generation / "pia_selected_candidates.csv"
    selected.to_csv(selected_path, index=False)
    selected.to_csv(generation / "simulation_batch.csv", index=False)
    (generation / "simulation_manifest.json").write_text(
        json.dumps(
            {
                "generation": 0,
                "candidate_count": 2,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        ),
        encoding="utf-8",
    )
    (generation / "generation_summary.json").write_text(
        json.dumps(
            {
                "generation": 0,
                "status": {"status": "pending_simulation"},
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "generation_state.jsonl").write_text(
        json.dumps(
            {
                "generation": 0,
                "selected_rows": 2,
                "imported_result_rows": 0,
                "must_resimulate": True,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "evolution_summary.json").write_text(
        json.dumps(
            {
                "stop_reason": "pending_simulation_results",
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ),
        encoding="utf-8",
    )
    return selected_path.read_bytes()


def test_maps_pending_pia_generation_to_product_candidates_and_events(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    output = tmp_path / "pia-output"
    original_selected = _write_pending_generation(output)

    mapping = PiaExperimentAdapter(repository, store).map_output(
        experiment.experiment_id,
        output,
        parameter_columns=("x1", "x2"),
    )

    assert mapping.experiment.state == ExperimentStatus.WAITING_FOR_SIMULATION
    assert [candidate.parameter_changes for candidate in mapping.candidates] == [
        {"x1": 1.25, "x2": 4.5},
        {"x1": 2.5, "x2": 3.0},
    ]
    assert all(candidate.must_resimulate is True for candidate in mapping.candidates)
    assert len(mapping.jobs) == 1
    assert mapping.jobs[0].status == SimulationJobStatus.WAITING_FOR_RESULTS
    assert mapping.jobs[0].candidate_ids == tuple(candidate.candidate_id for candidate in mapping.candidates)
    assert mapping.jobs[0].input_manifest_ref.endswith("/generation_000/simulation_manifest.json")
    assert mapping.jobs[0].batch_ref is not None
    assert repository.get_simulation_job(mapping.jobs[0].simulation_job_id) == mapping.jobs[0]
    events = repository.list_audit_events("experiment", experiment.experiment_id)
    generation_events = [event for event in events if event.action == "pia.generation.mapped"]
    assert len(generation_events) == 1
    assert generation_events[0].details["generation"] == 0
    assert generation_events[0].details["state"] == "waiting_for_simulation"
    selected_ref = next(ref for ref in mapping.artifacts if ref.key.endswith("pia_selected_candidates.csv"))
    assert store.resolve(selected_ref).read_bytes() == original_selected
    assert (output / "generation_000/pia_selected_candidates.csv").read_bytes() == original_selected


def test_mapping_resume_is_idempotent_and_does_not_duplicate_candidates(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    output = tmp_path / "pia-output"
    _write_pending_generation(output)
    adapter = PiaExperimentAdapter(repository, store)

    first = adapter.map_output(experiment.experiment_id, output, parameter_columns=("x1", "x2"))
    second = adapter.map_output(experiment.experiment_id, output, parameter_columns=("x1", "x2"))

    assert [candidate.candidate_id for candidate in second.candidates] == [
        candidate.candidate_id for candidate in first.candidates
    ]
    assert len(repository.list_candidates(experiment.experiment_id)) == 2
    assert [job.simulation_job_id for job in second.jobs] == [job.simulation_job_id for job in first.jobs]
    assert len(repository.list_simulation_jobs(experiment.project_id)) == 1
    events = repository.list_audit_events("experiment", experiment.experiment_id)
    assert sum(event.action == "pia.generation.mapped" for event in events) == 1


def test_mapping_rejects_weakened_boundary_without_mutating_experiment(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    output = tmp_path / "pia-output"
    _write_pending_generation(output)
    selected_path = output / "generation_000/pia_selected_candidates.csv"
    selected = pd.read_csv(selected_path)
    selected["must_resimulate"] = False
    selected.to_csv(selected_path, index=False)

    with pytest.raises(ValueError, match="must_resimulate"):
        PiaExperimentAdapter(repository, store).map_output(
            experiment.experiment_id,
            output,
            parameter_columns=("x1", "x2"),
        )

    assert repository.get_experiment(experiment.experiment_id).state == ExperimentStatus.READY
    assert repository.list_candidates(experiment.experiment_id) == []


def test_experiment_service_delegates_pia_evolution_to_registered_adapter(pia_product_context):
    repository, _, experiment, _ = pia_product_context
    sentinel = object()

    class Adapter:
        def run(self, experiment_id, **kwargs):
            assert experiment_id == experiment.experiment_id
            assert kwargs == {"budget": 3}
            return sentinel

    service = ExperimentService(repository, pia_adapter=Adapter())

    assert service.run_pia_evolution(experiment.experiment_id, budget=3) is sentinel


def test_adapter_wraps_native_evolution_runner_and_resume_loader(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    history = pd.DataFrame([{"x1": 1.0}])
    pool = pd.DataFrame([{"x1": 2.0}])
    calls = []

    def runner(actual_history, actual_pool, config, output_dir, **kwargs):
        calls.append((actual_history, actual_pool, config, output_dir, kwargs))
        _write_pending_generation(output_dir)
        return {"stop_reason": "pending_simulation_results"}

    def resume_loader(output_dir, generation):
        return {"output_dir": Path(output_dir), "generation": generation}

    adapter = PiaExperimentAdapter(repository, store, runner=runner, resume_loader=resume_loader)
    output = tmp_path / "pia-output"

    mapping = adapter.run(
        experiment.experiment_id,
        history=history,
        candidates=pool,
        config={"parameter_columns": ["x1", "x2"]},
        output_dir=output,
        generations=2,
    )

    assert mapping.experiment.state == ExperimentStatus.WAITING_FOR_SIMULATION
    assert calls == [(history, pool, {"parameter_columns": ["x1", "x2"]}, output, {"generations": 2})]
    assert adapter.load_resume_state(output, 0) == {"output_dir": output, "generation": 0}


def test_completed_pia_output_maps_to_completed_experiment(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    output = tmp_path / "pia-output"
    _write_pending_generation(output)
    summary_path = output / "generation_000" / "generation_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["status"] = {"status": "results_imported", "mode": "local_fixture"}
    summary["must_resimulate"] = False
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    imported = pd.read_csv(output / "generation_000" / "simulation_batch.csv")
    imported["must_resimulate"] = False
    imported.to_csv(output / "generation_000" / "imported_results.csv", index=False)
    evolution_path = output / "evolution_summary.json"
    evolution = json.loads(evolution_path.read_text(encoding="utf-8"))
    evolution["stop_reason"] = "max_generations"
    evolution_path.write_text(json.dumps(evolution), encoding="utf-8")

    mapping = PiaExperimentAdapter(repository, store).map_output(
        experiment.experiment_id,
        output,
        parameter_columns=("x1", "x2"),
    )

    assert mapping.experiment.state == ExperimentStatus.COMPLETED
    assert mapping.jobs[0].status == SimulationJobStatus.COMPLETED
    event = next(event for event in repository.list_audit_events("experiment", experiment.experiment_id) if event.action == "pia.generation.mapped")
    assert event.details["state"] == "completed"


def test_mapping_publishes_only_declared_and_boundary_validated_pia_artifacts(pia_product_context):
    repository, store, experiment, tmp_path = pia_product_context
    output = tmp_path / "pia-output"
    _write_pending_generation(output)
    (output / "unrelated_secret.txt").write_text("do not publish", encoding="utf-8")

    mapping = PiaExperimentAdapter(repository, store).map_output(
        experiment.experiment_id,
        output,
        parameter_columns=("x1", "x2"),
    )

    assert all(not ref.key.endswith("unrelated_secret.txt") for ref in mapping.artifacts)

    summary_path = output / "generation_000" / "generation_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["engineering_validity"] = "physical_validation"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="engineering_validity"):
        PiaExperimentAdapter(repository, LocalArtifactStore(tmp_path / "other-artifacts")).map_output(
            experiment.experiment_id,
            output,
            parameter_columns=("x1", "x2"),
        )
