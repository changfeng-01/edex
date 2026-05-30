import json
import os
import subprocess
import sys
from pathlib import Path


def test_sky130_mainline_require_real_ngspice_rejects_mock_fallback(tmp_path: Path):
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
            "--require-real-ngspice",
            "--sweep",
            str(sweep_path),
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=_clean_pdk_env(),
    )

    assert result.returncode == 2
    assert "require-real-ngspice" in result.stderr
    assert not (output_root / "mainline_validation.json").exists()


def test_sky130_mainline_require_real_ngspice_fails_when_toolchain_missing(tmp_path: Path):
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

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-mainline",
            "--mock-dataset-json",
            str(rows_path),
            "--require-real-ngspice",
            "--pdk-root",
            str(tmp_path / "missing_pdk"),
            "--ngspice-cmd",
            "definitely_missing_ngspice",
            "--sweep",
            str(sweep_path),
            "--output-root",
            str(tmp_path / "mainline"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=_clean_pdk_env(),
    )

    assert result.returncode == 2
    assert "real ngspice" in result.stderr.lower()


def _clean_pdk_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PDK_ROOT", None)
    env.pop("SKYWATER_PDK_ROOT", None)
    return env


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title require real fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "require_real_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {"ports": [{"name": "vout", "role": "output_v"}]},
    }
