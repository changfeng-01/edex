import json
from pathlib import Path

from goa_eval.cli import build_parser, main


def test_demo_cli_writes_product_package_and_frontend_bundle(tmp_path: Path):
    product_demo_root = tmp_path / "outputs" / "product_demo"
    frontend_data_root = tmp_path / "frontend" / "public" / "demo_data"
    demo_run_dir = tmp_path / "outputs" / "demo_mainline" / "public_demo"

    result = main(
        [
            "demo",
            "--output-root",
            str(product_demo_root),
            "--frontend-data-root",
            str(frontend_data_root),
            "--demo-run-dir",
            str(demo_run_dir),
        ]
    )

    assert result == 0
    case_dir = product_demo_root / "public_demo"
    dashboard_summary = case_dir / "06_dashboard_data" / "dashboard_summary.json"
    assert dashboard_summary.exists()
    assert (frontend_data_root / "public_demo" / "dashboard_summary.json").read_bytes() == dashboard_summary.read_bytes()

    summary = json.loads(dashboard_summary.read_text(encoding="utf-8"))
    assert summary["evidence"]["data_source"] == "real_simulation_csv"
    assert summary["evidence"]["engineering_validity"] == "simulation_only"

    manifest = json.loads((case_dir / "demo_mainline_manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"]["module"] == "python -m goa_eval.cli demo"
    assert manifest["command"]["console_script"] == "circuitpilot demo"
    assert manifest["case_id"] == "public_demo"
    assert manifest["input_files"]["waveform"] == "examples/sample_waveform.csv"
    assert manifest["input_files"]["param_space"] == "examples/sample_params.yaml"
    assert manifest["output_directories"]["product_demo_case_dir"].endswith("outputs/product_demo/public_demo")
    assert manifest["evidence_boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def test_demo_parser_accepts_one_click_defaults():
    args = build_parser().parse_args(["demo"])

    assert args.command == "demo"
    assert args.case_id == "public_demo"
    assert args.waveform == "examples/sample_waveform.csv"
    assert args.param_space == "examples/sample_params.yaml"
    assert args.seed == 42
