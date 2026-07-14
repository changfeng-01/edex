from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from goa_eval.product.experiment_service import ExperimentService
from goa_eval.product.settings import ProductSettings
from goa_eval.product_api.app import create_product_app
from goa_eval.product_api.dependencies import ProductContainer


def generator(_config, max_candidates, seed):
    return [
        {
            "parameter_changes": {"t1_width_um": 10.0 + seed + index},
            "reason_codes": ["reduce_ripple"],
            "selection_score": 0.8,
        }
        for index in range(max_candidates)
    ]


@pytest.fixture
def phase2_api(tmp_path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'phase2.db'}",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=False,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)
    container.experiment_service = ExperimentService(container.repository, generators={"rule": generator})
    client = TestClient(create_product_app(container))
    workspace = client.post("/api/v1/workspaces", json={"name": "GOA team"}).json()["data"]
    project = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace["workspace_id"],
            "name": "GOA",
            "circuit_profile_id": "goa_8k",
            "spec_revision_id": "spec_v1",
        },
    ).json()["data"]
    baseline = client.post(
        f"/api/v1/projects/{project['project_id']}/design-versions",
        json={"label": "baseline"},
    ).json()["data"]
    return client, container, project, baseline, tmp_path


def create_experiment(client, project, baseline):
    response = client.post(
        f"/api/v1/projects/{project['project_id']}/experiments",
        json={
            "baseline_design_version_id": baseline["design_version_id"],
            "strategy_config": {"strategy": "rule"},
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_experiment_generation_approval_and_rejection_contracts(phase2_api):
    client, _, project, baseline, _ = phase2_api
    experiment = create_experiment(client, project, baseline)
    generated = client.post(
        f"/api/v1/experiments/{experiment['experiment_id']}/candidates:generate",
        json={"strategy": "rule", "max_candidates": 2, "seed": 17},
    )
    candidates = generated.json()["data"]
    approved = client.post(
        f"/api/v1/candidates/{candidates[0]['candidate_id']}:approve",
        json={"actor_id": "reviewer"},
    )
    rejected = client.post(
        f"/api/v1/candidates/{candidates[1]['candidate_id']}:reject",
        json={"actor_id": "reviewer", "reason": "unsafe"},
    )

    assert generated.status_code == 201
    assert approved.status_code == 200
    assert rejected.status_code == 200
    assert approved.json()["data"]["status"] == "approved"
    assert rejected.json()["data"]["status"] == "rejected"
    assert all(candidate["must_resimulate"] is True for candidate in candidates)


def test_manual_job_export_preview_commit_and_retry_contracts(phase2_api):
    client, container, project, baseline, _ = phase2_api
    experiment = create_experiment(client, project, baseline)
    candidate = client.post(
        f"/api/v1/experiments/{experiment['experiment_id']}/candidates:generate",
        json={"strategy": "rule", "max_candidates": 1, "seed": 7},
    ).json()["data"][0]
    candidate = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}:approve",
        json={"actor_id": "reviewer"},
    ).json()["data"]
    job = client.post(
        "/api/v1/simulation-jobs",
        json={"candidate_ids": [candidate["candidate_id"]], "adapter_type": "manual"},
    ).json()["data"]
    exported_response = client.post(f"/api/v1/simulation-jobs/{job['simulation_job_id']}:export")
    exported = exported_response.json()["data"]
    batch_ref = container.artifact_store.ref_from_uri(exported["batch_ref"]["uri"])
    batch = pd.read_csv(container.artifact_store.resolve(batch_ref))
    results = pd.DataFrame(
        {
            "candidate_id": batch["candidate_id"],
            "parameter_hash": batch["parameter_hash"],
            "overall_score": [0.91],
            "hard_constraint_passed": [True],
        }
    ).to_csv(index=False).encode()
    preview = client.post(
        f"/api/v1/simulation-jobs/{job['simulation_job_id']}/imports:preview",
        files={"results": ("results.csv", results, "text/csv")},
    )
    committed = client.post(
        f"/api/v1/simulation-jobs/{job['simulation_job_id']}/imports:commit",
        json={"manifest_sha256": preview.json()["data"]["manifest_sha256"]},
    )

    assert exported_response.status_code == 200
    assert preview.status_code == 200
    assert committed.status_code == 200
    assert committed.json()["data"]["status"] == "completed"
    assert container.settings.job_execution_enabled is False


def test_phase2_errors_are_stable_and_path_safe(phase2_api):
    client, _, project, baseline, tmp_path = phase2_api
    experiment = create_experiment(client, project, baseline)
    candidate = client.post(
        f"/api/v1/experiments/{experiment['experiment_id']}/candidates:generate",
        json={"strategy": "rule", "max_candidates": 1, "seed": 7},
    ).json()["data"][0]
    conflict = client.post(
        "/api/v1/simulation-jobs",
        json={"candidate_ids": [candidate["candidate_id"]], "adapter_type": "manual"},
    )
    missing = client.get("/api/v1/comparisons/comparison_missing")
    invalid = client.post(
        "/api/v1/simulation-jobs/job_missing/imports:preview",
        files={"results": ("results.csv", b"bad", "text/csv")},
    )

    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "EXPERIMENT_STATE_CONFLICT"
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "COMPARISON_NOT_FOUND"
    assert invalid.status_code == 404
    for response in (conflict, missing, invalid):
        body = response.json()
        assert {"error_code", "details", "retryable", "artifact_refs"} <= set(body)
        assert str(tmp_path.resolve()) not in response.text


def test_comparison_create_get_and_candidate_confirmation_conflict(phase2_api):
    client, _, project, baseline, _ = phase2_api
    result = client.post(
        f"/api/v1/projects/{project['project_id']}/design-versions",
        json={"label": "result", "parent_version_id": baseline["design_version_id"]},
    ).json()["data"]
    response = client.post(
        "/api/v1/comparisons",
        json={
            "project_id": project["project_id"],
            "baseline_design_version_id": baseline["design_version_id"],
            "result_design_version_id": result["design_version_id"],
            "baseline_analysis_run_id": None,
            "result_analysis_run_id": None,
        },
    )
    comparison = response.json()["data"]
    loaded = client.get(f"/api/v1/comparisons/{comparison['comparison_id']}")

    assert response.status_code == 201
    assert comparison["verdict"] == "evidence_insufficient"
    assert loaded.status_code == 200
    assert loaded.json()["data"] == comparison

