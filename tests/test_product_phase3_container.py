import sys

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
        def availability(self):
            return AdapterAvailability(True, (), ("execute",))

        def build_execution(self, _job, _store, work_dir):
            command = "from pathlib import Path; Path('result.csv').write_text('candidate_id,score\\na,1\\n')"
            return ExecutionCommand(
                (sys.executable, "-c", command),
                cwd=work_dir,
                evidence={"evidence_type": "mock_fixture", "reportable_as_real_ngspice": False},
                output_files=("result.csv",),
            )

    registry = SimulatorRegistry({"fixture": Adapter, "empyrean_offline": EmpyreanOfflineAdapter})
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
    input_manifest = container.artifact_store.put_bytes("phase3/test/input_manifest.json", b"{}")

    created = client.post(
        "/api/v1/simulation-jobs",
        json={
            "candidate_ids": [candidate["candidate_id"]],
            "adapter_type": "fixture",
            "input_manifest_ref": input_manifest.uri,
        },
    )
    job = created.json()["data"]
    queued = client.post(f"/api/v1/simulation-jobs/{job['simulation_job_id']}:queue")
    executed = client.post(f"/api/v1/simulation-jobs/{job['simulation_job_id']}:execute")
    persisted = container.repository.get_simulation_job(job["simulation_job_id"])

    assert created.status_code == 201
    assert queued.json()["data"]["status"] == "queued"
    assert executed.status_code == 200
    assert persisted.status.value == "waiting_for_results"
    assert persisted.batch_ref is not None
    assert persisted.command_manifest_ref is not None
    assert container.artifact_store.ref_from_uri(persisted.result_manifest_ref)
    assert container.artifact_store.ref_from_uri(persisted.command_manifest_ref)

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
