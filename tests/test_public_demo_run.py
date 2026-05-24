import csv
import json
import subprocess
import sys
from pathlib import Path


EXPECTED_DEMO_FILES = {
    "real_summary.json",
    "score_summary.json",
    "real_metrics.csv",
    "optimization_dataset.csv",
    "recommendations.md",
    "next_candidates.csv",
    "next_candidates.md",
    "llm_parameter_analysis.md",
    "llm_parameter_analysis.json",
    "run_manifest_real.json",
}

DASHBOARD_FILES = {
    "real_summary.json",
    "score_summary.json",
    "real_metrics.csv",
    "optimization_dataset.csv",
}


def run_public_demo(output_dir: Path, frontend_data_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/build_public_demo.py",
            "--output-dir",
            str(output_dir),
            "--frontend-data-dir",
            str(frontend_data_dir),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_build_public_demo_writes_public_bundle_and_dashboard_data(tmp_path):
    output_dir = tmp_path / "demo_run"
    frontend_data_dir = tmp_path / "frontend_data"

    result = run_public_demo(output_dir, frontend_data_dir)

    assert result.returncode == 0, result.stderr
    assert EXPECTED_DEMO_FILES <= {path.name for path in output_dir.iterdir()}
    assert (output_dir / "figures" / "block_stability_heatmap.png").stat().st_size > 0

    summary = json.loads((output_dir / "real_summary.json").read_text(encoding="utf-8"))
    assert summary["run_id"] == "public_demo_run"
    assert summary["run_timestamp"] == "2026-05-22T00:00:00"
    assert summary["data_source"] == "real_simulation_csv"
    assert summary["engineering_validity"] == "simulation_only"

    manifest = json.loads((output_dir / "run_manifest_real.json").read_text(encoding="utf-8"))
    assert manifest["code_version_or_git_commit"] == "public_demo_snapshot"

    candidate_text = (output_dir / "next_candidates.md").read_text(encoding="utf-8")
    assert "simulation_only" in candidate_text

    analysis = json.loads((output_dir / "llm_parameter_analysis.json").read_text(encoding="utf-8"))
    assert analysis["boundary"]["engineering_validity"] == "simulation_only"
    assert analysis["metadata"]["mock_response"] is True
    assert analysis["input_files"]["summary"] == "examples/demo_run/real_summary.json"

    for filename in DASHBOARD_FILES:
        assert (frontend_data_dir / filename).read_bytes() == (output_dir / filename).read_bytes()
    assert (frontend_data_dir / "figures" / "voh_trend.png").stat().st_size > 0


def test_build_public_demo_is_deterministic_for_candidate_generation(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = run_public_demo(first, tmp_path / "frontend_first")
    second_result = run_public_demo(second, tmp_path / "frontend_second")

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert (first / "next_candidates.csv").read_text(encoding="utf-8") == (
        second / "next_candidates.csv"
    ).read_text(encoding="utf-8")
    assert (first / "real_summary.json").read_text(encoding="utf-8") == (
        second / "real_summary.json"
    ).read_text(encoding="utf-8")

    with (first / "next_candidates.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 10
    assert rows[0]["candidate_id"] == "cand_001"
    assert rows[0]["strategy"] == "constrained_random"
