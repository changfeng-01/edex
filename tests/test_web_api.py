from pathlib import Path

from fastapi.testclient import TestClient

from goa_eval.web.app import create_app
from goa_eval.web.schemas import WebApiSettings


def client_for(root: Path) -> TestClient:
    app = create_app(WebApiSettings(web_cases_root=root))
    return TestClient(app)


def test_health_returns_ok(tmp_path: Path):
    response = client_for(tmp_path / "web_cases").get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "circuitpilot-upload-api"}


def test_upload_waveform_creates_completed_case_and_bundle(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform, Path("examples/sample_params.yaml").open("rb") as params:
        response = client.post(
            "/api/cases",
            data={"case_id": "sample_case", "generate_candidates": "true"},
            files={
                "waveform": ("waveform.csv", waveform, "text/csv"),
                "params": ("params.yaml", params, "application/x-yaml"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "sample_case"
    assert payload["status"] == "completed"
    assert payload["evidence_boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }

    status_response = client.get("/api/cases/sample_case/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["status"] == "completed"
    assert status["case_id"] == "sample_case"
    assert status["evidence_boundary"]["engineering_validity"] == "simulation_only"

    bundle_response = client.get("/api/cases/sample_case/bundle")
    assert bundle_response.status_code == 200
    bundle = bundle_response.json()
    assert bundle["case_id"] == "sample_case"
    assert set(bundle) >= {"summary", "tables", "figures", "reports", "manifest"}
    assert bundle["summary"]["evidence"]["data_source"] == "real_simulation_csv"
    assert bundle["summary"]["evidence"]["engineering_validity"] == "simulation_only"
    assert bundle["summary"]["evidence"]["must_resimulate"] is True
    assert bundle["tables"]["candidates"]["rows"]
    assert bundle["figures"]
    assert bundle["figures"][0]["url"].startswith("/api/cases/sample_case/assets/")
    assert bundle["reports"]
    assert bundle["reports"][0]["url"].startswith("/api/cases/sample_case/assets/")

    report_response = client.get(bundle["reports"][0]["url"])
    assert report_response.status_code == 200
    assert "data_source = real_simulation_csv" in report_response.text
    assert "engineering_validity = simulation_only" in report_response.text
    assert "must_resimulate = true" in report_response.text


def test_missing_waveform_returns_clear_error(tmp_path: Path):
    response = client_for(tmp_path / "web_cases").post("/api/cases", data={"case_id": "missing_waveform"})

    assert response.status_code == 400
    assert "waveform.csv is required" in response.json()["detail"]


def test_upload_rejects_dangerous_filename(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform:
        response = client.post(
            "/api/cases",
            data={"case_id": "bad_upload"},
            files={"waveform": ("../../secret.csv", waveform, "text/csv")},
        )

    assert response.status_code == 400
    assert "invalid filename" in response.json()["detail"]


def test_asset_path_escape_is_rejected(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    response = client.get("/api/cases/sample_case/assets/../../secret.csv")

    assert response.status_code in {400, 404}
