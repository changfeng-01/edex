import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_sky130_mainline_cli_mock_writes_lightweight_bundle(tmp_path: Path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
max_runs: 4
parameters:
  m1_width:
    target: M1.W
    values: ["1u", "2u"]
  load_cap:
    target: CLOAD.C
    values: ["1pF", "2pF"]
""",
        encoding="utf-8",
    )
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(
        """
target:
  metric: Max_overlap_ratio
  threshold: 0.1
candidate_replay:
  top_n: 2
validation_matrix:
  - name: long_hold
    max_runs: 1
    parameters:
      tran_stop:
        target: .tran:stop
        values: ["20n"]
  - name: pvt_load
    max_runs: 8
    parameters:
      corner:
        target: .lib:corner
        values: ["tt", "ss"]
      temperature:
        target: .temp
        values: ["25", "125"]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "mainline"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-mainline",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--validation-config",
            str(validation_path),
            "--rounds",
            "1",
            "--max-runs-per-round",
            "2",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=_clean_pdk_env(),
    )

    assert result.returncode == 0, result.stderr
    assert (output_root / "optimization_leaderboard.csv").exists()
    assert (output_root / "best_next_candidates.csv").exists()
    assert (output_root / "mainline_validation.json").exists()
    assert (output_root / "sky130_mainline_report.md").exists()

    payload = json.loads((output_root / "mainline_validation.json").read_text(encoding="utf-8"))
    assert payload["engineering_validity"] == "simulation_only"
    assert payload["data_source"] == "real_simulation_csv"
    assert payload["mode"] == "lightweight"
    assert payload["full_validation"] is False
    assert payload["preflight"]["mock_ngspice"] is True
    assert payload["artifacts"]["leaderboard"] == "optimization_leaderboard.csv"
    assert payload["artifacts"]["best_next_candidates"] == "best_next_candidates.csv"
    statuses = {case["validation_name"]: case["validation_status"] for case in payload["validation_cases"]}
    assert statuses["long_hold"] in {"skipped", "passed", "failed", "not_evaluable"}
    assert statuses["pvt_load"] == "skipped"
    assert "pending" not in set(statuses.values())

    report = (output_root / "sky130_mainline_report.md").read_text(encoding="utf-8")
    assert "simulation_only" in report
    assert "physical validation" not in report.lower()
    assert "silicon validation" not in report.lower()
    assert "lab validation" not in report.lower()


def test_sky130_mainline_cli_full_validation_marks_matrix_enabled(tmp_path: Path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
parameters:
  m1_width:
    target: M1.W
    values: ["1u"]
""",
        encoding="utf-8",
    )
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(
        """
target:
  metric: Max_overlap_ratio
  threshold: 999
validation_matrix:
  - name: pvt_load
    max_runs: 2
    parameters:
      temperature:
        target: .temp
        values: ["25", "125"]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "mainline_full"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-mainline",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--validation-config",
            str(validation_path),
            "--rounds",
            "1",
            "--max-runs-per-round",
            "1",
            "--full-validation",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=_clean_pdk_env(),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((output_root / "mainline_validation.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "full_validation"
    assert payload["full_validation"] is True
    case = payload["validation_cases"][0]
    assert case["validation_name"] == "pvt_load"
    assert case["full_validation_enabled"] is True
    assert case["validation_status"] in {"passed", "failed", "not_evaluable", "skipped"}
    assert case["validation_status"] != "pending"


def test_sky130_mainline_real_environment_smoke_can_be_skipped(tmp_path: Path):
    pdk_root = Path("tools/volare-pdks/sky130A")
    ngspice_bin = Path("tools/ngspice/Spice64/bin/ngspice.exe")
    if not pdk_root.exists() or not ngspice_bin.exists():
        pytest.skip("local SKY130 PDK or ngspice is not available")

    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
parameters:
  m1_width:
    target: M1.W
    values: ["1u"]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "real_smoke"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-mainline",
            "--mock-dataset-json",
            str(rows_path),
            "--sweep",
            str(sweep_path),
            "--pdk-root",
            str(pdk_root),
            "--ngspice-cmd",
            str(ngspice_bin),
            "--rounds",
            "1",
            "--max-runs-per-round",
            "1",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((output_root / "mainline_validation.json").read_text(encoding="utf-8"))
    assert payload["engineering_validity"] == "simulation_only"


def _clean_pdk_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PDK_ROOT", None)
    env.pop("SKYWATER_PDK_ROOT", None)
    return env


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title sky130 mainline fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            "CLOAD vout 0 1pF",
            "V1 vin 0 pulse(0 1.8 1n 1n 1n 5n 20n)",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "mainline_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {
            "ports": [
                {"name": "vout", "role": "output_v"},
                {"name": "vaux", "role": "output_v"},
                {"name": "vthird", "role": "output_v"},
            ]
        },
    }
