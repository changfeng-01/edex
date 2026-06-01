import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient

from goa_eval.web_api.app import create_app
from goa_eval.web_api.config import DashboardApiSettings


def client_for(root: Path, enable_build_api: bool = False) -> TestClient:
    app = create_app(DashboardApiSettings(product_demo_root=root, enable_build_api=enable_build_api))
    return TestClient(app)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def make_case(root: Path, case_id: str = "public_demo") -> Path:
    case_dir = root / case_id
    dashboard_dir = case_dir / "06_dashboard_data"
    figures_dir = case_dir / "05_figures"
    report_dir = case_dir / "07_report"
    summary = {
        "case_id": case_id,
        "run_id": "run-1",
        "overall_status": "FAIL_RIPPLE",
        "overall_score": 62,
        "hard_constraint_passed": False,
        "validation_status": "awaiting_rerun_results",
        "candidate_status": "available",
        "evidence": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "optimizer_claim_level": "candidate_suggestion_only",
        },
    }
    tables = {
        "run_summary": {"file": "run_summary_table.csv", "rows": [{"case_id": case_id}]},
        "constraints": {"file": "constraint_table.csv", "rows": [{"constraint": "Max_ripple"}]},
        "candidates": {"file": "top_candidates_table.csv", "rows": [{"status": "available"}]},
        "before_after": {"file": "before_after_table.csv", "rows": [{"status": "awaiting_rerun_results"}]},
    }
    figures = {
        "waveform": {
            "title": "Waveform Overview",
            "file": "fig01_waveform_overview.png",
            "size_bytes": 8,
        }
    }
    manifest = {
        "case_id": case_id,
        "validation_status": "awaiting_rerun_results",
        "candidate_status": "available",
        "evidence": summary["evidence"],
    }
    write_json(dashboard_dir / "dashboard_summary.json", summary)
    write_json(dashboard_dir / "dashboard_tables.json", tables)
    write_json(dashboard_dir / "dashboard_figures.json", figures)
    write_json(dashboard_dir / "presentation_manifest.json", manifest)
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "fig01_waveform_overview.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "executive_summary.md").write_text("engineering_validity = simulation_only\n", encoding="utf-8")
    return case_dir


def test_health_returns_ok(tmp_path):
    response = client_for(tmp_path / "missing").get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "circuitpilot-dashboard-api"}


def test_cases_empty_when_product_demo_root_missing(tmp_path):
    response = client_for(tmp_path / "missing").get("/api/cases")

    assert response.status_code == 200
    assert response.json() == {"cases": []}


def test_cases_discovers_product_demo_case(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)

    response = client_for(root).get("/api/cases")

    assert response.status_code == 200
    assert response.json()["cases"][0]["case_id"] == "public_demo"
    assert response.json()["cases"][0]["has_manifest"] is True
    assert response.json()["cases"][0]["has_summary"] is True
    assert response.json()["cases"][0]["validation_status"] == "awaiting_rerun_results"
    assert response.json()["cases"][0]["candidate_status"] == "available"


def test_summary_reads_dashboard_summary_and_preserves_evidence_boundary(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)

    response = client_for(root).get("/api/cases/public_demo/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_status"] == "awaiting_rerun_results"
    assert payload["evidence"]["data_source"] == "real_simulation_csv"
    assert payload["evidence"]["engineering_validity"] == "simulation_only"


def test_missing_summary_returns_structured_empty_state(tmp_path):
    response = client_for(tmp_path / "product_demo").get("/api/cases/public_demo/summary")

    assert response.status_code == 200
    assert response.json()["missing"] is True
    assert response.json()["evidence"]["engineering_validity"] == "simulation_only"


def test_tables_reads_dashboard_tables_json(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)

    response = client_for(root).get("/api/cases/public_demo/tables")

    assert response.status_code == 200
    assert response.json()["constraints"]["rows"] == [{"constraint": "Max_ripple"}]


def test_tables_falls_back_to_csv_when_dashboard_tables_json_missing(tmp_path):
    root = tmp_path / "product_demo"
    case_dir = make_case(root)
    (case_dir / "06_dashboard_data" / "dashboard_tables.json").unlink()
    write_csv(case_dir / "02_evaluation" / "run_summary_table.csv", [{"case_id": "public_demo"}])
    write_csv(case_dir / "02_evaluation" / "constraint_table.csv", [{"constraint": "Max_ripple"}])
    write_csv(case_dir / "03_candidates" / "top_candidates_table.csv", [{"status": "available"}])
    write_csv(case_dir / "04_validation" / "before_after_table.csv", [{"status": "awaiting_rerun_results"}])

    response = client_for(root).get("/api/cases/public_demo/tables")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_summary"]["rows"] == [{"case_id": "public_demo"}]
    assert payload["before_after"]["rows"] == [{"status": "awaiting_rerun_results"}]


def test_tables_return_missing_payload_for_absent_csv(tmp_path):
    root = tmp_path / "product_demo"
    case_dir = make_case(root)
    (case_dir / "06_dashboard_data" / "dashboard_tables.json").unlink()

    response = client_for(root).get("/api/cases/public_demo/tables")

    assert response.status_code == 200
    assert response.json()["run_summary"]["rows"] == []
    assert response.json()["run_summary"]["missing"] is True


def test_figures_list_and_file_endpoint(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)
    client = client_for(root)

    response = client.get("/api/cases/public_demo/figures")
    assert response.status_code == 200
    assert response.json()["figures"][0]["url"] == "/api/cases/public_demo/figures/fig01_waveform_overview.png"

    image_response = client.get("/api/cases/public_demo/figures/fig01_waveform_overview.png")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"


def test_reports_list_and_markdown_endpoint(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)
    client = client_for(root)

    response = client.get("/api/cases/public_demo/reports")
    assert response.status_code == 200
    assert response.json()["reports"][0]["name"] == "executive_summary.md"

    report_response = client.get("/api/cases/public_demo/reports/executive_summary.md")
    assert report_response.status_code == 200
    assert "engineering_validity = simulation_only" in report_response.text


def test_bundle_returns_dashboard_first_screen_payload(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)

    response = client_for(root).get("/api/cases/public_demo/bundle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "public_demo"
    assert payload["summary"]["validation_status"] == "awaiting_rerun_results"
    assert payload["figures"][0]["exists"] is True
    assert payload["reports"][0]["exists"] is True
    assert payload["manifest"]["evidence"]["engineering_validity"] == "simulation_only"


def test_invalid_case_id_is_rejected(tmp_path):
    response = client_for(tmp_path / "product_demo").get("/api/cases/../summary")

    assert response.status_code in {400, 404}


def test_invalid_filename_is_rejected(tmp_path):
    root = tmp_path / "product_demo"
    make_case(root)

    response = client_for(root).get("/api/cases/public_demo/figures/..png")

    assert response.status_code == 400


def test_build_api_disabled_by_default(tmp_path):
    response = client_for(tmp_path / "product_demo").post(
        "/api/cases/public_demo/build-demo",
        json={"input_dir": "examples/demo_run", "output_dir": "outputs/product_demo"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "build API disabled"
