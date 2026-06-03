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


def test_sample_demo_case_creates_completed_case_and_readable_bundle(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    response = client.post("/api/demo/sample-case")

    assert response.status_code == 200
    payload = response.json()
    case_id = payload["case_id"]
    assert case_id.startswith("demo_")
    assert payload["status"] == "completed"
    assert payload["bundle_url"] == f"/api/cases/{case_id}/bundle"
    assert payload["evidence_boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }

    bundle_response = client.get(payload["bundle_url"])
    assert bundle_response.status_code == 200
    bundle = bundle_response.json()
    assert bundle["case_id"] == case_id
    assert bundle["summary"]["evidence"]["engineering_validity"] == "simulation_only"
    assert bundle["summary"]["evidence"]["must_resimulate"] is True


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


def test_preview_upload_returns_input_preview_and_evidence_boundary(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform, Path("examples/sample_params.yaml").open("rb") as params:
        response = client.post(
            "/api/cases/preview",
            data={"case_id": "preview_case", "output_node_pattern": "o{index}"},
            files={
                "waveform": ("waveform.csv", waveform, "text/csv"),
                "params": ("params.yaml", params, "application/x-yaml"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "preview_case"
    assert payload["status"] == "preview_ready"
    assert payload["evidence_boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }

    preview = payload["preview"]
    assert preview["ready_for_analysis"] is True
    assert preview["row_count"] > 0
    assert preview["column_count"] == 4
    assert preview["time_column_original"] == "XVAL"
    assert preview["time_column_normalized"] == "time"
    assert preview["detected_output_nodes"][:3] == ["o1", "o2", "o3"]
    assert preview["detected_output_node_count"] == 3
    assert preview["params_summary"]["has_param_space"] is True
    assert preview["params_summary"]["parameter_count"] == 8
    assert "capacitance" in preview["params_summary"]["parameter_names"]

    get_response = client.get("/api/cases/preview_case/input-preview")
    assert get_response.status_code == 200
    assert get_response.json()["case_id"] == "preview_case"
    assert get_response.json()["preview"]["time_column_original"] == "XVAL"


def test_preview_detects_time_aliases_and_output_node_aliases(tmp_path: Path):
    waveform_path = tmp_path / "custom_waveform.csv"
    waveform_path.write_text("time_ns,OUT1,gate2,gout3\n0,0.1,0.2,0.3\n10,1.1,1.2,1.3\n", encoding="utf-8")
    client = client_for(tmp_path / "web_cases")

    with waveform_path.open("rb") as waveform:
        response = client.post(
            "/api/cases/preview",
            data={"case_id": "alias_case"},
            files={"waveform": ("waveform.csv", waveform, "text/csv")},
        )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["time_column_original"] == "time_ns"
    assert preview["guessed_time_unit"] == "ns"
    assert preview["detected_output_nodes"] == ["out1", "gate2", "gout3"]
    assert preview["ready_for_analysis"] is True


def test_preview_missing_waveform_returns_clear_error(tmp_path: Path):
    response = client_for(tmp_path / "web_cases").post("/api/cases/preview", data={"case_id": "missing_waveform"})

    assert response.status_code == 400
    assert "waveform.csv is required" in response.json()["detail"]


def test_preview_rejects_dangerous_filename(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform:
        response = client.post(
            "/api/cases/preview",
            data={"case_id": "bad_preview_upload"},
            files={"waveform": ("../../secret.csv", waveform, "text/csv")},
        )

    assert response.status_code == 400
    assert "invalid filename" in response.json()["detail"]


def test_preview_get_missing_preview_returns_404(tmp_path: Path):
    response = client_for(tmp_path / "web_cases").get("/api/cases/no_preview/input-preview")

    assert response.status_code == 404
    assert "input preview not found" in response.json()["detail"]


def test_preview_netlist_summary_survives_parser_limitations(tmp_path: Path):
    netlist_path = tmp_path / "sample.sp"
    netlist_path.write_text(
        "\n".join(
            [
                ".SUBCKT inv in out vdd vss",
                "M1 out in vdd vdd pmos W=1u L=0.1u",
                "XM2 out in vss vss nmos W=1u L=0.1u",
                "C1 out vss 1p",
                "R1 out vss 10k",
                ".ENDS inv",
            ]
        ),
        encoding="utf-8",
    )
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform, netlist_path.open("rb") as netlist:
        response = client.post(
            "/api/cases/preview",
            data={"case_id": "netlist_preview"},
            files={
                "waveform": ("waveform.csv", waveform, "text/csv"),
                "netlist": ("source_netlist.sp", netlist, "text/plain"),
            },
        )

    assert response.status_code == 200
    netlist_summary = response.json()["preview"]["netlist_summary"]
    assert netlist_summary["netlist_available"] is True
    assert netlist_summary["mos_like_device_count"] == 2
    assert netlist_summary["capacitor_like_count"] == 1
    assert netlist_summary["resistor_like_count"] == 1
    assert netlist_summary["subckt_count"] >= 1


def test_asset_path_escape_is_rejected(tmp_path: Path):
    client = client_for(tmp_path / "web_cases")

    response = client.get("/api/cases/sample_case/assets/../../secret.csv")

    assert response.status_code in {400, 404}
