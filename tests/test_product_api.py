from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goa_eval.product.models import AnalysisRunRecord, AnalysisStatus, new_id
from goa_eval.product.settings import ProductSettings
from goa_eval.product_api.app import create_product_app
from goa_eval.product_api.dependencies import ProductContainer


@pytest.fixture
def api_context(tmp_path: Path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'test-product.db'}",
        artifact_root=tmp_path / "test-artifacts",
        job_execution_enabled=False,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)
    client = TestClient(create_product_app(container))
    return client, container, tmp_path


def _create_project(client: TestClient):
    workspace = client.post("/api/v1/workspaces", json={"name": "GOA team"}).json()["data"]
    project = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace["workspace_id"],
            "name": "720-stage GOA",
            "circuit_profile_id": "goa_8k",
            "spec_revision_id": "spec_v1",
        },
    ).json()["data"]
    return workspace, project


def _create_version(client: TestClient, project_id: str, label: str = "baseline"):
    return client.post(
        f"/api/v1/projects/{project_id}/design-versions",
        json={"label": label},
    ).json()["data"]


def _preview(client: TestClient, version_id: str, waveform: Path = Path("examples/sample_waveform.csv")):
    with waveform.open("rb") as waveform_handle, Path("examples/sample_params.yaml").open("rb") as params_handle:
        return client.post(
            f"/api/v1/design-versions/{version_id}/inputs/preview",
            files={
                "waveform": ("waveform.csv", waveform_handle, "text/csv"),
                "params": ("params.yaml", params_handle, "application/yaml"),
            },
        )


def test_container_uses_only_injected_temporary_storage(api_context):
    _, container, tmp_path = api_context

    assert Path(container.settings.artifact_root).is_relative_to(tmp_path)
    assert str(tmp_path) in container.settings.database_url
    assert "outputs/product" not in container.settings.database_url
    assert container.settings.job_execution_enabled is False


def test_workspace_project_and_version_routes_are_versioned_and_scoped(api_context):
    client, _, _ = api_context
    workspace, project = _create_project(client)
    version = _create_version(client, project["project_id"])

    workspace_response = client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/projects")
    project_response = client.get(f"/api/v1/projects/{project['project_id']}")
    overview_response = client.get(f"/api/v1/projects/{project['project_id']}/overview")
    versions_response = client.get(f"/api/v1/projects/{project['project_id']}/design-versions")
    version_response = client.get(f"/api/v1/design-versions/{version['design_version_id']}")

    for response in (
        workspace_response,
        project_response,
        overview_response,
        versions_response,
        version_response,
    ):
        assert response.status_code == 200
        assert response.json()["schema_version"] == "1.0"
    assert workspace_response.json()["data"] == [project]
    assert overview_response.json()["data"]["version_count"] == 1
    assert versions_response.json()["data"] == [version]


def test_workspace_creation_returns_201_and_invalid_profile_has_stable_error(api_context):
    client, _, _ = api_context
    workspace = client.post("/api/v1/workspaces", json={"name": "GOA team"})
    invalid = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace.json()["data"]["workspace_id"],
            "name": "invalid",
            "circuit_profile_id": "not_a_profile",
            "spec_revision_id": "spec_v1",
        },
    )

    assert workspace.status_code == 201
    assert workspace.json()["schema_version"] == "1.0"
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error_code": "CIRCUIT_PROFILE_INVALID",
        "message": "Circuit profile is invalid.",
        "details": {},
        "retryable": False,
        "artifact_refs": [],
    }


def test_input_preview_publishes_snapshot_without_exposing_server_paths(api_context):
    client, _, tmp_path = api_context
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])

    response = _preview(client, version["design_version_id"])

    assert response.status_code == 201
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["data"]["preview_status"] == "preview_ready"
    assert body["data"]["manifest_ref"]["uri"].startswith("artifact://")
    assert str(tmp_path.resolve()) not in response.text


def test_input_preview_accepts_optional_netlist_and_image(api_context, tmp_path: Path):
    client, _, _ = api_context
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])
    netlist = tmp_path / "source.spice"
    netlist.write_text("* display-only source\n.end\n", encoding="utf-8")
    image = tmp_path / "plot.png"
    image.write_bytes(b"display-only")

    with Path("examples/sample_waveform.csv").open("rb") as waveform, netlist.open("rb") as net, image.open("rb") as img:
        response = client.post(
            f"/api/v1/design-versions/{version['design_version_id']}/inputs/preview",
            files=[
                ("waveform", ("waveform.csv", waveform, "text/csv")),
                ("netlist", ("source_netlist.spice", net, "text/plain")),
                ("attachments", ("plot.png", img, "image/png")),
            ],
        )

    assert response.status_code == 201
    assert response.json()["data"]["preview"]["attachments_summary"]["image_count"] == 1


def test_malformed_and_unsafe_inputs_return_stable_errors(api_context, tmp_path: Path):
    client, _, _ = api_context
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])
    malformed = tmp_path / "bad.csv"
    malformed.write_text("unsupported\n1\n", encoding="utf-8")

    malformed_response = _preview(client, version["design_version_id"], malformed)
    with Path("examples/sample_waveform.csv").open("rb") as waveform:
        unsafe_response = client.post(
            f"/api/v1/design-versions/{version['design_version_id']}/inputs/preview",
            files={"waveform": ("../waveform.csv", waveform, "text/csv")},
        )

    assert malformed_response.status_code == 422
    assert malformed_response.json()["error_code"] == "INPUT_PREVIEW_FAILED"
    assert unsafe_response.status_code == 422
    assert unsafe_response.json()["error_code"] == "INPUT_PREVIEW_FAILED"


def test_analysis_routes_execute_and_return_bundle_issues_and_evidence(api_context):
    client, _, _ = api_context
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])
    snapshot = _preview(client, version["design_version_id"]).json()["data"]

    response = client.post(
        f"/api/v1/design-versions/{version['design_version_id']}/analysis-runs",
        json={"input_manifest_ref": snapshot["manifest_ref"], "case_id": "product_api"},
    )

    assert response.status_code == 201
    run = response.json()["data"]
    run_id = run["analysis_run_id"]
    assert run["status"] == "completed"
    for suffix in ("", "/bundle", "/issues", "/evidence"):
        resource = client.get(f"/api/v1/analysis-runs/{run_id}{suffix}")
        assert resource.status_code == 200
        assert resource.json()["schema_version"] == "1.0"
    evidence = client.get(f"/api/v1/analysis-runs/{run_id}/evidence").json()["data"]
    assert evidence["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    assert evidence["records"]
    issues = client.get(f"/api/v1/analysis-runs/{run_id}/issues").json()["data"]
    assert issues["issues"]


def test_unknown_resource_and_state_conflict_use_stable_errors(api_context):
    client, container, _ = api_context
    missing = client.get("/api/v1/projects/project_missing")
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])
    snapshot = _preview(client, version["design_version_id"]).json()["data"]
    active = AnalysisRunRecord(
        analysis_run_id=new_id("run"),
        design_version_id=version["design_version_id"],
        input_manifest_ref=snapshot["manifest_ref"]["uri"],
        spec_revision_id="spec_v1",
        profile_revision_id="profile_v1",
        status=AnalysisStatus.RUNNING,
    )
    container.repository.add_analysis_run(active)
    conflict = client.post(
        f"/api/v1/design-versions/{version['design_version_id']}/analysis-runs",
        json={"input_manifest_ref": snapshot["manifest_ref"], "case_id": "conflict"},
    )

    assert missing.status_code == 404
    assert missing.json()["error_code"] == "PROJECT_NOT_FOUND"
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "ANALYSIS_STATE_CONFLICT"


def test_internal_analysis_failure_never_leaks_traceback(api_context):
    client, container, _ = api_context
    _, project = _create_project(client)
    version = _create_version(client, project["project_id"])
    snapshot = _preview(client, version["design_version_id"]).json()["data"]

    class BrokenAnalysisService:
        def run_analysis(self, **_kwargs):
            raise RuntimeError("private path C:/secret/traceback")

    container.analysis_service = BrokenAnalysisService()
    response = client.post(
        f"/api/v1/design-versions/{version['design_version_id']}/analysis-runs",
        json={"input_manifest_ref": snapshot["manifest_ref"], "case_id": "broken"},
    )

    assert response.status_code == 500
    assert response.json()["error_code"] == "ANALYSIS_EXECUTION_FAILED"
    assert "traceback" not in response.text.lower()
    assert "C:/secret" not in response.text
