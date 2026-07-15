import importlib
import importlib.util
import json

import pytest

from fastapi.testclient import TestClient

from goa_eval.product.artifact_store import ArtifactIntegrityError, LocalArtifactStore
from goa_eval.product.profile_service import ProfileService
from goa_eval.product.project_service import ProjectService
from goa_eval.product.settings import ProductSettings
from goa_eval.product_api.app import create_product_app
from goa_eval.product_api.dependencies import ProductContainer


def test_profile_service_freezes_a_validated_revision(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  demo_ota:
    type: analog_amplifier
    aliases: [demo]
    boundary:
      data_source: real_simulation_csv
      engineering_validity: simulation_only
      must_resimulate: true
    required_analyses: [ac]
    node_rules:
      output: [v(out)]
    metrics:
      dc_gain_db:
        source: ac_metrics
        source_analysis: ac
        unit: dB
        minimum: 40dB
    candidate_rules:
      dc_gain_db:
        - semantic_tags: [gain_device_width]
          direction: increase
""".strip(),
        encoding="utf-8",
    )
    semantics_file = tmp_path / "semantics.yaml"
    semantics_file.write_text(
        """
parameters:
  m1_width:
    values: [1um]
    semantic_tags: [gain_device_width]
""".strip(),
        encoding="utf-8",
    )
    spec = importlib.util.find_spec("goa_eval.product.profile_service")
    assert spec is not None, "Phase 4 ProfileService module must exist"
    module = importlib.import_module("goa_eval.product.profile_service")
    service = module.ProfileService(
        LocalArtifactStore(tmp_path / "artifacts"),
        profile_path=profile_file,
        semantics_path=semantics_file,
    )

    revision = service.get_profile("demo")

    assert revision["profile_id"] == "demo_ota"
    assert revision["revision_id"].startswith("profile_")
    assert len(revision["source_hash"]) == 64
    assert len(revision["semantics_hash"]) == 64
    assert revision["supported_analyses"] == ["ac"]
    assert revision["required_metrics"] == ["dc_gain_db"]
    assert revision["node_rules"] == {"output": ["v(out)"]}
    assert revision["units"] == {"dc_gain_db": "dB"}
    assert revision["validation"] == {"valid": True, "errors": []}
    assert revision["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    ref = service.artifact_store.ref_from_uri(revision["snapshot_ref"]["uri"])
    frozen = json.loads(service.artifact_store.resolve(ref).read_text(encoding="utf-8"))
    assert frozen["revision_id"] == revision["revision_id"]
    assert frozen["profile"]["metrics"]["dc_gain_db"]["minimum"] == 40.0


def test_product_api_exposes_read_only_profile_routes(tmp_path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'product.db'}",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=False,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)
    client = TestClient(create_product_app(container))

    listed = client.get("/api/v1/profiles")
    detailed = client.get("/api/v1/profiles/ota")
    validated = client.get("/api/v1/profiles:validate")
    missing = client.get("/api/v1/profiles/not_a_profile")

    assert listed.status_code == 200
    assert {item["profile_id"] for item in listed.json()["data"]} >= {
        "default",
        "goa_8k_lcd_reference",
        "ota_general",
    }
    assert detailed.status_code == 200
    assert detailed.json()["data"]["profile_id"] == "ota_general"
    assert detailed.json()["data"]["snapshot_ref"]["uri"].startswith("artifact://profiles/")
    assert validated.status_code == 200
    assert validated.json()["data"]["valid"] is True
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "CIRCUIT_PROFILE_NOT_FOUND"


def test_profile_service_rejects_noncanonical_boundary_instead_of_rewriting_it(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  demo:
    aliases: []
    boundary:
      data_source: synthetic_fixture_csv
      engineering_validity: test_only
      must_resimulate: false
    metrics: {}
""".strip(),
        encoding="utf-8",
    )
    service = importlib.import_module("goa_eval.product.profile_service").ProfileService(
        LocalArtifactStore(tmp_path / "artifacts"),
        profile_path=profile_file,
    )

    with pytest.raises(ValueError, match="canonical evidence boundary"):
        service.get_profile("demo")


def test_profile_revision_collision_verifies_expected_payload_hash(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  demo:
    aliases: []
    boundary:
      data_source: real_simulation_csv
      engineering_validity: simulation_only
      must_resimulate: true
    metrics: {}
""".strip(),
        encoding="utf-8",
    )
    module = importlib.import_module("goa_eval.product.profile_service")
    clean_store = LocalArtifactStore(tmp_path / "clean")
    clean_revision = module.ProfileService(clean_store, profile_path=profile_file).get_profile("demo")
    key = clean_revision["snapshot_ref"]["key"]
    tampered_store = LocalArtifactStore(tmp_path / "tampered")
    tampered_store.put_bytes(key, b'{"tampered":true}\n')

    with pytest.raises(ArtifactIntegrityError):
        module.ProfileService(tampered_store, profile_path=profile_file).get_profile("demo")


def test_project_api_rejects_profile_that_fails_semantics_validation(tmp_path):
    settings = ProductSettings(
        database_url=f"sqlite:///{tmp_path / 'product.db'}",
        artifact_root=tmp_path / "artifacts",
        job_execution_enabled=False,
    )
    container = ProductContainer.from_settings(settings, create_tables=True)
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  invalid:
    aliases: []
    boundary:
      data_source: real_simulation_csv
      engineering_validity: simulation_only
      must_resimulate: true
    metrics: {}
    candidate_rules:
      score:
        - semantic_tags: [not_registered]
          direction: increase
""".strip(),
        encoding="utf-8",
    )
    profile_service = ProfileService(container.artifact_store, profile_path=profile_file)
    container.project_service = ProjectService(
        container.repository,
        container.artifact_store,
        profile_service=profile_service,
    )
    client = TestClient(create_product_app(container))
    workspace = client.post("/api/v1/workspaces", json={"name": "demo"}).json()["data"]

    response = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": workspace["workspace_id"],
            "name": "invalid",
            "circuit_profile_id": "invalid",
            "spec_revision_id": "spec_v1",
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "CIRCUIT_PROFILE_INVALID"
