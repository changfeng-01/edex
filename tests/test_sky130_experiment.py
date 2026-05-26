import json
import subprocess
import sys
from pathlib import Path

from goa_eval.sky130_experiment import build_preflight_report


def test_sky130_preflight_reports_missing_toolchain_as_skipped(tmp_path: Path):
    report = build_preflight_report(
        pdk_root=tmp_path / "missing_pdk",
        ngspice=tmp_path / "missing_ngspice.exe",
        output_dir=tmp_path / "sky130",
        mock_if_unavailable=True,
    )

    assert report["experiment"] == "sky130_ngspice"
    assert report["status"] == "skipped_missing_toolchain"
    assert report["can_run_real_ngspice"] is False
    assert report["mock_if_unavailable"] is True
    assert report["engineering_validity"] == "simulation_only"
    assert report["tracked_tool_policy"] == "external_or_local_ignored_only"
    assert "tools/" in report["ignored_paths"]


def test_sky130_experiment_cli_writes_preflight_and_report(tmp_path: Path):
    output_dir = tmp_path / "sky130_experiment"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-experiment",
            "--pdk-root",
            str(tmp_path / "missing_pdk"),
            "--ngspice",
            str(tmp_path / "missing_ngspice.exe"),
            "--output-dir",
            str(output_dir),
            "--mock-if-unavailable",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "sky130_experiment_preflight.json").exists()
    assert (output_dir / "sky130_ngspice_experiment.md").exists()

    preflight = json.loads((output_dir / "sky130_experiment_preflight.json").read_text(encoding="utf-8"))
    assert preflight["status"] == "skipped_missing_toolchain"
    assert preflight["engineering_validity"] == "simulation_only"

    report = (output_dir / "sky130_ngspice_experiment.md").read_text(encoding="utf-8")
    assert "SKY130 / ngspice Experiment Branch" in report
    assert "simulation_only" in report
    assert "not physical validation" in report
