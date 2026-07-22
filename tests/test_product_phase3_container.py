import json
import sys

import pandas as pd
from fastapi.testclient import TestClient

from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.adapters.empyrean_offline import EmpyreanOfflineAdapter
from goa_eval.product.job_runner import ExecutionCommand, ProductJobRunner
from goa_eval.product.pia_experiment_adapter import PiaExperimentAdapter
from goa_eval.product.settings import ProductSettings
from goa_eval.product.simulation_job_service import SimulationJobService
from goa_eval.product.simulator_registry import AdapterAvailability, SimulatorRegistry
from goa_eval.product_api.app import create_product_app
from goa_eval.product_api.dependencies import ProductContainer


def test_product_container_wires_phase3_services(tmp_path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'product.db'}",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=False,
    )

    container = ProductContainer.from_settings(settings, create_tables=True)

    assert isinstance(container.simulator_registry, SimulatorRegistry)
    assert isinstance(container.job_runner, ProductJobRunner)
    assert isinstance(container.experiment_service._pia_adapter, PiaExperimentAdapter)
    assert container.simulation_job_service._simulator_registry is container.simulator_registry


def test_phase3_execution_is_reachable_through_product_api_and_persists_outputs(tmp_path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'product.db'}",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=True,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)

    class Adapter:
        result_output_name = "simulation_results.csv"

        def availability(self):
            return AdapterAvailability(True, (), ("render", "execute", "import"))

        def build_execution(self, job, store, work_dir):
            manifest = json.loads(
                store.resolve(store.ref_from_uri(job.input_manifest_ref)).read_text(encoding="utf-8")
            )
            assert manifest["input_snapshot_id"]
            batch = pd.read_csv(store.resolve(job.batch_ref))
            row = batch.iloc[0]
            result = pd.DataFrame(
                [
                    {
                        "candidate_id": row["candidate_id"],
                        "parameter_hash": row["parameter_hash"],
                        "overall_score": 91.0,
                        "hard_constraint_passed": True,
                        "data_source": "real_simulation_csv",
                        "engineering_validity": "simulation_only",
                        "must_resimulate": True,
                    }
                ]
            ).to_csv(index=False)
            command = f"from pathlib import Path; Path('simulation_results.csv').write_text({result!r})"
            return ExecutionCommand(
                (sys.executable, "-c", command),
                cwd=work_dir,
                evidence={"evidence_type": "synthetic_execution_fixture"},
                output_files=("simulation_results.csv",),
            )

        def import_results(self, result_path, *, expected_candidate_ids=()):
            frame = pd.read_csv(result_path)
            assert set(frame["candidate_id"].astype(str)) == set(expected_candidate_ids)
            return frame

    registry = SimulatorRegistry(
        {"trusted_execution_fixture": Adapter, "empyrean_offline": EmpyreanOfflineAdapter}
    )
    container.simulator_registry = registry
    container.simulation_job_service = SimulationJobService(
        container.repository,
        container.artifact_store,
        container.project_service,
        registry,
    )
    container.job_runner = ProductJobRunner(
        container.repository,
        container.artifact_store,
        registry,
        settings,
    )

    def generator(_config, maximum, _seed):
        return [{"parameter_changes": {"x": float(index + 1)}} for index in range(maximum)]

    container.experiment_service = ExperimentService(container.repository, generators={"rule": generator})
    client = TestClient(create_product_app(container))
    workspace = client.post("/api/v1/workspaces", json={"name": "team"}).json()["data"]
    project = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace["workspace_id"],
            "name": "GOA",
            "circuit_profile_id": "goa_8k",
            "spec_revision_id": "v1",
        },
    ).json()["data"]
    baseline = client.post(
        f"/api/v1/projects/{project['project_id']}/design-versions",
        json={"label": "baseline"},
    ).json()["data"]
    experiment = client.post(
        f"/api/v1/projects/{project['project_id']}/experiments",
        json={"baseline_design_version_id": baseline["design_version_id"], "strategy_config": {}},
    ).json()["data"]
    candidates = client.post(
        f"/api/v1/experiments/{experiment['experiment_id']}/candidates:generate",
        json={"strategy": "rule", "max_candidates": 2, "seed": 1},
    ).json()["data"]
    candidate = candidates[0]
    candidate = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}:approve",
        json={"actor_id": "reviewer"},
    ).json()["data"]
    netlist = tmp_path / "source_netlist.spice"
    netlist.write_text("V1 out 0 1\n.op\n.end\n", encoding="utf-8")
    with (
        open("examples/sample_waveform.csv", "rb") as waveform,
        open("examples/sample_params.yaml", "rb") as params,
        netlist.open("rb") as netlist_handle,
    ):
        snapshot = client.post(
            f"/api/v1/design-versions/{baseline['design_version_id']}/inputs/preview",
            files={
                "waveform": ("waveform.csv", waveform, "text/csv"),
                "params": ("params.yaml", params, "application/yaml"),
                "netlist": ("source_netlist.spice", netlist_handle, "text/plain"),
            },
        ).json()["data"]

    created = client.post(
        "/api/v1/simulation-jobs",
        json={
            "candidate_ids": [candidate["candidate_id"]],
            "adapter_type": "trusted_execution_fixture",
            "input_manifest_ref": snapshot["manifest_ref"]["uri"],
        },
    )
    job = created.json()["data"]
    execution_contract = json.loads(
        container.artifact_store.resolve(
            container.artifact_store.ref_from_uri(job["command_manifest_ref"])
        ).read_text(encoding="utf-8")
    )
    assert execution_contract["adapter_input_manifest_ref"] == job["input_manifest_ref"]
    queued = client.post(f"/api/v1/simulation-jobs/{job['simulation_job_id']}:queue")
    executed = client.post(f"/api/v1/simulation-jobs/{job['simulation_job_id']}:execute")
    persisted = container.repository.get_simulation_job(job["simulation_job_id"])

    assert created.status_code == 201
    assert queued.json()["data"]["status"] == "queued"
    assert executed.status_code == 200
    assert executed.json()["data"]["status"] == "completed"
    assert persisted.status.value == "completed"
    assert persisted.batch_ref is not None
    assert persisted.command_manifest_ref is not None
    assert container.artifact_store.ref_from_uri(persisted.result_manifest_ref)
    assert container.artifact_store.ref_from_uri(persisted.command_manifest_ref)
    assert container.repository.get_candidate(candidate["candidate_id"]).status.value == "resimulated"

    offline_candidate = client.post(
        f"/api/v1/candidates/{candidates[1]['candidate_id']}:approve",
        json={"actor_id": "reviewer"},
    ).json()["data"]
    offline_created = client.post(
        "/api/v1/simulation-jobs",
        json={
            "candidate_ids": [offline_candidate["candidate_id"]],
            "adapter_type": "empyrean_offline",
        },
    ).json()["data"]
    offline_exported = client.post(
        f"/api/v1/simulation-jobs/{offline_created['simulation_job_id']}:export"
    ).json()["data"]
    assert offline_exported["status"] == "waiting_for_results"
    assert container.artifact_store.ref_from_uri(offline_exported["command_manifest_ref"])
