import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.empyrean.case_importer import run_empyrean_import
from goa_eval.empyrean.runner import run_empyrean_toolchain


def _write_waveform_only_case(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "time": [0.0, 1e-6, 2e-6, 3e-6, 4e-6],
            "o1": [0.0, 6.0, 6.0, 0.0, 0.0],
            "o2": [0.0, 0.0, 6.0, 6.0, 0.0],
        }
    ).to_csv(path / "waveform.csv", index=False)


def test_empyrean_import_waveform_only_completes_basic_evaluation(tmp_path: Path):
    source = tmp_path / "case"
    output = tmp_path / "out"
    _write_waveform_only_case(source)

    run_empyrean_import(
        input_dir=source,
        output_dir=output,
        case_id="waveform_only",
        spec_path=Path("config/spec.yaml"),
        stage_count=2,
    )

    assert (output / "normalized_waveform.csv").exists()
    assert (output / "real_summary.json").exists()
    assert (output / "score_summary.json").exists()
    assert (output / "physical_verification_summary.json").exists()
    physical = json.loads((output / "physical_verification_summary.json").read_text(encoding="utf-8"))
    assert physical["drc"]["status"] == "not_provided"
    manifest = json.loads((output / "empyrean_case_manifest.json").read_text(encoding="utf-8"))
    assert manifest["tool_invocation"] is False
    assert manifest["evidence_boundary"]["no_local_empyrean_tool_invocation"] is True


def test_empyrean_import_cli_writes_candidates_for_example_case(tmp_path: Path):
    output = tmp_path / "empyrean_case"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "empyrean-import",
            "--input-dir",
            "examples/empyrean_case",
            "--output-dir",
            str(output),
            "--case-id",
            "demo_empyrean_case",
            "--stage-count",
            "3",
            "--generate-candidates",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "next_candidates.csv").exists()
    assert (output / "next_candidates.md").exists()
    summary = json.loads((output / "real_summary.json").read_text(encoding="utf-8"))
    assert summary["data_source"] == "exported_empyrean_files"
    assert summary["engineering_validity"] == "simulation_or_tool_export_only"
    physical = json.loads((output / "physical_verification_summary.json").read_text(encoding="utf-8"))
    assert physical["drc"]["status"] == "passed"
    parasitic = json.loads((output / "parasitic_summary.json").read_text(encoding="utf-8"))
    assert parasitic["has_rc_data"] is True


def test_empyrean_runner_refuses_tool_execution():
    with pytest.raises(RuntimeError, match="Use empyrean-import with exported files"):
        run_empyrean_toolchain()
