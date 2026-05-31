import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_DIRS = {
    "01_input_snapshot",
    "02_evaluation",
    "03_candidates",
    "04_validation",
    "05_figures",
    "06_dashboard_data",
    "07_report",
}

EXPECTED_FIGURES = {
    "fig01_waveform_overview.png",
    "fig02_constraint_status.png",
    "fig03_metric_comparison.png",
    "fig04_candidate_ranking.png",
    "fig05_before_after_comparison.png",
    "fig06_evidence_card.png",
}

EXPECTED_TABLE_COLUMNS = {
    "02_evaluation/run_summary_table.csv": [
        "case_id",
        "run_id",
        "overall_status",
        "overall_score",
        "hard_constraint_passed",
        "stage_count",
        "resolved_output_node_count",
        "data_source",
        "engineering_validity",
        "evidence_level",
        "simulation_backend",
        "optimizer_claim_level",
        "validation_status",
        "candidate_status",
    ],
    "02_evaluation/constraint_table.csv": [
        "constraint",
        "status",
        "current_value",
        "threshold",
        "reason",
    ],
    "03_candidates/top_candidates_table.csv": [
        "rank",
        "candidate_id",
        "priority",
        "parameter_changes",
        "trigger_metric",
        "strategy",
        "search_score",
        "status",
        "data_source",
        "engineering_validity",
    ],
    "04_validation/before_after_table.csv": [
        "metric",
        "before_value",
        "after_value",
        "delta",
        "status",
        "unit",
    ],
}


def run_product_demo(input_dir: Path, output_dir: Path, case_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "product-demo",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--case-id",
            case_id,
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_product_demo_cli_writes_handoff_ready_package(tmp_path):
    result = run_product_demo(Path("examples/demo_run"), tmp_path / "product_demo", "public_demo")

    assert result.returncode == 0, result.stderr
    case_dir = tmp_path / "product_demo" / "public_demo"
    assert EXPECTED_DIRS <= {path.name for path in case_dir.iterdir() if path.is_dir()}

    for figure in EXPECTED_FIGURES:
        path = case_dir / "05_figures" / figure
        assert path.exists()
        assert path.stat().st_size > 0

    for rel_path, columns in EXPECTED_TABLE_COLUMNS.items():
        with (case_dir / rel_path).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == columns

    manifest = json.loads((case_dir / "06_dashboard_data" / "presentation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_id"] == "public_demo"
    assert manifest["evidence"]["data_source"] == "real_simulation_csv"
    assert manifest["evidence"]["engineering_validity"] == "simulation_only"
    assert manifest["validation_status"] == "awaiting_rerun_results"

    executive = (case_dir / "07_report" / "executive_summary.md").read_text(encoding="utf-8")
    assert "engineering_validity = simulation_only" in executive


def test_product_demo_missing_validation_does_not_fake_improvement(tmp_path):
    input_dir = tmp_path / "demo_run"
    shutil.copytree(Path("examples/demo_run"), input_dir)
    validation = input_dir / "validation_summary.csv"
    if validation.exists():
        validation.unlink()

    result = run_product_demo(input_dir, tmp_path / "product_demo", "missing_validation")

    assert result.returncode == 0, result.stderr
    before_after = (tmp_path / "product_demo" / "missing_validation" / "04_validation" / "before_after_table.csv").read_text(
        encoding="utf-8"
    )
    assert "awaiting_rerun_results" in before_after
    assert "improved" not in before_after.lower()


def test_product_demo_missing_candidate_data_writes_status_table(tmp_path):
    input_dir = tmp_path / "demo_run"
    shutil.copytree(Path("examples/demo_run"), input_dir)
    for name in ["next_candidates.csv", "best_next_candidates.csv", "optimization_leaderboard.csv"]:
        path = input_dir / name
        if path.exists():
            path.unlink()

    result = run_product_demo(input_dir, tmp_path / "product_demo", "missing_candidates")

    assert result.returncode == 0, result.stderr
    candidate_table = tmp_path / "product_demo" / "missing_candidates" / "03_candidates" / "top_candidates_table.csv"
    assert "awaiting_candidate_generation" in candidate_table.read_text(encoding="utf-8")


def test_product_demo_repeated_runs_keep_core_manifest_stable(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = run_product_demo(Path("examples/demo_run"), first, "public_demo")
    second_result = run_product_demo(Path("examples/demo_run"), second, "public_demo")

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr

    first_manifest = json.loads((first / "public_demo" / "06_dashboard_data" / "presentation_manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "public_demo" / "06_dashboard_data" / "presentation_manifest.json").read_text(encoding="utf-8"))
    assert first_manifest["case_id"] == second_manifest["case_id"]
    assert first_manifest["evidence"] == second_manifest["evidence"]
    assert first_manifest["tables"] == second_manifest["tables"]
    assert first_manifest["figures"] == second_manifest["figures"]

    first_columns = (first / "public_demo" / "02_evaluation" / "run_summary_table.csv").read_text(encoding="utf-8").splitlines()[0]
    second_columns = (second / "public_demo" / "02_evaluation" / "run_summary_table.csv").read_text(encoding="utf-8").splitlines()[0]
    assert first_columns == second_columns
