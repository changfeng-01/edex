from pathlib import Path

from fastapi.testclient import TestClient

from goa_eval.dashboard_api import create_app
from goa_eval.product_demo.workflow import run_product_demo


def test_dashboard_api_bundle_returns_product_demo_payload(tmp_path: Path):
    product_demo_root = tmp_path / "product_demo"
    run_product_demo(Path("examples/demo_run"), product_demo_root, "api_demo")

    client = TestClient(create_app(product_demo_root=product_demo_root))
    response = client.get("/api/cases/api_demo/bundle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["caseId"] == "api_demo"
    assert payload["summary"]["case_id"] == "api_demo"
    assert payload["summary"]["evidence"]["data_source"] == "real_simulation_csv"
    assert payload["summary"]["evidence"]["engineering_validity"] == "simulation_only"
    assert payload["tables"]["constraints"]["rows"]
    assert payload["figures"][0]["url"].startswith("/api/cases/api_demo/files/figures/")
    assert payload["manifest"]["case_id"] == "api_demo"
    assert payload["reports"][0]["content"]
    assert payload["resourceErrors"] == []


def test_dashboard_build_api_is_disabled_by_default(tmp_path: Path):
    client = TestClient(create_app(product_demo_root=tmp_path / "product_demo"))

    response = client.post("/api/build", json={"case_id": "public_demo"})

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]
