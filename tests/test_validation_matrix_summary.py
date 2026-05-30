import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_mainline_validation_payload_and_summary_include_matrix_rollup(tmp_path: Path):
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
  - name: nominal_rerun
    max_runs: 1
  - name: long_hold
    max_runs: 1
    parameters:
      tran_stop:
        target: .tran:stop
        values: ["20n"]
  - name: pvt_load
    max_runs: 1
    parameters:
      temperature:
        target: .temp
        values: ["25"]
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
            "1",
            "--full-validation",
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
    summary = payload["validation_matrix_summary"]
    frame = pd.read_csv(output_root / "validation_summary.csv")

    assert summary["validation_case_count"] == 3
    assert summary["validation_pass_count"] + summary["validation_fail_count"] + summary["validation_not_evaluable_count"] == 3
    assert 0.0 <= summary["validation_matrix_pass_rate"] <= 1.0
    assert summary["worst_case_name"] in {"nominal_rerun", "long_hold", "pvt_load", ""}
    assert payload["optimizer_claim_level"] in {
        "candidate_generated",
        "nominal_rerun_passed",
        "validation_matrix_passed",
    }
    for column in [
        "validation_matrix_pass_rate",
        "validation_case_count",
        "validation_pass_count",
        "validation_fail_count",
        "validation_not_evaluable_count",
        "worst_case_name",
        "worst_case_metric",
        "worst_case_value",
    ]:
        assert column in frame.columns


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title validation matrix fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "validation_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {
            "ports": [
                {"name": "vout", "role": "output_v"},
                {"name": "vaux", "role": "output_v"},
            ]
        },
    }
