import json
from pathlib import Path

from fastapi.testclient import TestClient

from goa_eval.web.app import create_app
from goa_eval.web.schemas import WebApiSettings


def client_for(root: Path, **settings) -> TestClient:
    app = create_app(WebApiSettings(web_cases_root=root, **settings))
    return TestClient(app)


def test_health_returns_ok(tmp_path: Path):
    response = client_for(tmp_path / "web_cases").get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "circuitpilot-upload-api"}


def test_upload_waveform_creates_completed_case_and_bundle(tmp_path: Path):
    web_cases_root = tmp_path / "web_cases"
    client = client_for(web_cases_root)

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

    product_demo_case_dir = web_cases_root / "sample_case" / "product_demo" / "sample_case"
    persisted_summary = product_demo_case_dir / "06_dashboard_data" / "dashboard_summary.json"
    persisted_manifest = product_demo_case_dir / "06_dashboard_data" / "presentation_manifest.json"
    for path in [persisted_summary, persisted_manifest]:
        evidence = json.loads(path.read_text(encoding="utf-8"))["evidence"]
        assert evidence["data_source"] == "real_simulation_csv"
        assert evidence["engineering_validity"] == "simulation_only"
        assert evidence["must_resimulate"] is True

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
            data={"case_id": "preview_case", "stage_count": "4", "output_node_pattern": "o{index}"},
            files={
                "waveform": ("waveform.csv", waveform, "text/csv"),
                "params": ("params.yaml", params, "application/x-yaml"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    case_id = payload["case_id"]
    assert case_id.startswith("case_")
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
    assert preview["expected_stage_count"] == 4
    assert preview["observed_stage_count"] == 3
    assert preview["output_coverage_ratio"] == 0.75
    assert preview["coverage_status"] == "partial"
    assert preview["params_summary"]["has_param_space"] is True
    assert preview["params_summary"]["parameter_count"] == 8
    assert "capacitance" in preview["params_summary"]["parameter_names"]

    get_response = client.get(f"/api/cases/{case_id}/input-preview")
    assert get_response.status_code == 200
    assert get_response.json()["case_id"] == case_id
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


def test_required_write_auth_rejects_missing_and_wrong_key(tmp_path: Path) -> None:
    client = client_for(
        tmp_path / "web_cases",
        write_api_key="secret-key",
        require_write_auth=True,
    )

    assert client.post("/api/cases").status_code == 401
    assert client.post("/api/cases", headers={"Authorization": "Bearer wrong"}).status_code == 401
    authorized = client.post("/api/cases", headers={"Authorization": "Bearer secret-key"})
    assert authorized.status_code == 400
    assert "waveform.csv is required" in authorized.json()["detail"]


def test_required_write_auth_without_key_fails_at_startup(tmp_path: Path) -> None:
    try:
        create_app(WebApiSettings(web_cases_root=tmp_path, require_write_auth=True))
    except ValueError as exc:
        assert "CIRCUITPILOT_WRITE_API_KEY" in str(exc)
    else:
        raise AssertionError("create_app should reject missing required write key")


def test_existing_case_returns_conflict_without_deleting_files(tmp_path: Path) -> None:
    root = tmp_path / "web_cases"
    existing = root / "same_case"
    existing.mkdir(parents=True)
    sentinel = existing / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    client = client_for(root)

    with Path("examples/sample_waveform.csv").open("rb") as waveform:
        response = client.post(
            "/api/cases",
            data={"case_id": "same_case"},
            files={"waveform": ("waveform.csv", waveform, "text/csv")},
        )

    assert response.status_code == 409
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_preview_uses_generated_case_id_instead_of_client_id(tmp_path: Path) -> None:
    client = client_for(tmp_path / "web_cases")

    with Path("examples/sample_waveform.csv").open("rb") as waveform:
        response = client.post(
            "/api/cases/preview",
            data={"case_id": "requested_preview"},
            files={"waveform": ("waveform.csv", waveform, "text/csv")},
        )

    assert response.status_code == 200
    assert response.json()["case_id"].startswith("case_")
    assert response.json()["case_id"] != "requested_preview"


def test_waveform_upload_over_limit_returns_413(tmp_path: Path) -> None:
    client = client_for(tmp_path / "web_cases", max_waveform_bytes=4, max_request_bytes=8)

    response = client.post(
        "/api/cases",
        files={"waveform": ("waveform.csv", b"XVAL,v(o1)\n0,0\n", "text/csv")},
    )

    assert response.status_code == 413
    assert "waveform" in response.json()["detail"]
