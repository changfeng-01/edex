import json
import subprocess
import sys
from pathlib import Path


def test_public_demo_runner_generates_reproducible_outputs(tmp_path):
    output_dir = tmp_path / "public_demo"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_public_demo.py",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "examples/sample_waveform.csv" in result.stdout

    expected_files = {
        "real_metrics.csv",
        "real_summary.json",
        "score_summary.json",
        "optimization_dataset.csv",
        "diagnosis_report.md",
        "real_waveform_report.md",
        "recommendations.md",
        "run_manifest_real.json",
    }
    assert expected_files <= {path.name for path in output_dir.iterdir()}

    summary = json.loads((output_dir / "real_summary.json").read_text(encoding="utf-8"))
    assert summary["data_source"] == "real_simulation_csv"
    assert summary["engineering_validity"] == "simulation_only"

    manifest = json.loads((output_dir / "run_manifest_real.json").read_text(encoding="utf-8"))
    assert manifest["data_source"] == "real_simulation_csv"
    assert manifest["engineering_validity"] == "simulation_only"
    assert any(Path(path).as_posix().endswith("examples/sample_waveform.csv") for path in manifest["input_files"])
