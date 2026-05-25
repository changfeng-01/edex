import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.sky130_sweep import generate_sweep_points, rewrite_spice_parameters, _resolve_pdk_root


def _row() -> dict:
    return {
        "circuit_id": "amp_001",
        "base_circuit_id": "amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": "\n".join(
            [
                ".title sweep fixture",
                "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
                "M2 vout vin 0 0 NMOS W=1u L=0.15u",
                "CLOAD vout 0 1pF",
                ".END",
            ]
        ),
        "testbench_spice": "\n".join(
            [
                ".title sweep fixture",
                ".param ibias=10u",
                "VDD vdd 0 DC 1.8",
                "I1 ibias_node 0 DC 10uA",
                "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
                "R1 vout load 10k",
                "CLOAD load 0 1pF",
                "V1 vin 0 pulse(0 1.8 1n 1n 1n 5n 20n)",
                ".tran 1n 40n",
                ".end",
            ]
        ),
        "netlist_json": {"ports": [{"name": "vout", "role": "output_v"}, {"name": "vaux", "role": "output_v"}]},
    }


def test_generate_sweep_points_is_reproducible_and_limited():
    config = {
        "parameters": {
            "m1_width": {"target": "M1.W", "values": ["1u", "2u"]},
            "load_cap": {"target": "CLOAD.C", "values": ["1pF", "2pF"]},
        }
    }

    points = generate_sweep_points(config, max_runs=3)

    assert points == [
        {"m1_width": "1u", "load_cap": "1pF"},
        {"m1_width": "1u", "load_cap": "2pF"},
        {"m1_width": "2u", "load_cap": "1pF"},
    ]


def test_resolve_pdk_root_returns_absolute_path_for_relative_input(tmp_path, monkeypatch):
    pdk = tmp_path / "pdk"
    pdk.mkdir()
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_pdk_root(Path("pdk"), mock_ngspice=False)

    assert resolved == pdk.resolve()


def test_rewrite_spice_parameters_updates_param_devices_and_sources():
    text = _row()["testbench_spice"]
    targets = {
        "bias": {"target": ".param:ibias"},
        "m1_width": {"target": "M1.W"},
        "m1_length": {"target": "M1.L"},
        "load_cap": {"target": "CLOAD.C"},
        "drive_resistance": {"target": "R1.R"},
        "vdd": {"target": "VDD.dc_value"},
        "ibias": {"target": "I1.dc_value"},
        "new_param": {"target": ".param:new_gain"},
    }

    result = rewrite_spice_parameters(
        text,
        {
            "bias": "20u",
            "m1_width": "2u",
            "m1_length": "0.18u",
            "load_cap": "2pF",
            "drive_resistance": "12k",
            "vdd": "1.7",
            "ibias": "15uA",
            "new_param": "3",
        },
        targets,
    )

    assert result.success
    assert ".param ibias=20u" in result.text
    assert ".param new_gain=3" in result.text
    assert "M1 vout vin vdd vdd PMOS W=2u L=0.18u" in result.text
    assert "R1 vout load 12k" in result.text
    assert "CLOAD load 0 2pF" in result.text
    assert "VDD vdd 0 DC 1.7" in result.text
    assert "I1 ibias_node 0 DC 15uA" in result.text


def test_rewrite_spice_parameters_allows_mos_target_to_match_sky130_xmos_name():
    result = rewrite_spice_parameters(
        "XM1 out in 0 0 sky130_fd_pr__nfet_01v8 W=0.8u L=0.15u\n.end\n",
        {"m1_width": "1.2u"},
        {"m1_width": {"target": "M1.W"}},
    )

    assert result.success
    assert "XM1 out in 0 0 sky130_fd_pr__nfet_01v8 W=1.2u L=0.15u" in result.text


def test_rewrite_spice_parameters_updates_corner_temperature_and_transient_stop():
    text = "\n".join(
        [
            ".title validation matrix fixture",
            '.lib "sky130.lib.spice" tt',
            ".temp 25",
            ".tran 20p 4n",
            ".end",
        ]
    )

    result = rewrite_spice_parameters(
        text,
        {"corner": "ss", "temperature": "-40", "tran_stop": "20n"},
        {
            "corner": {"target": ".lib:corner"},
            "temperature": {"target": ".temp"},
            "tran_stop": {"target": ".tran:stop"},
        },
    )

    assert result.success
    assert '.lib "sky130.lib.spice" ss' in result.text
    assert ".temp -40" in result.text
    assert ".tran 20p 20n" in result.text


def test_rewrite_spice_parameters_inserts_missing_temperature_before_end():
    result = rewrite_spice_parameters(
        ".title validation matrix fixture\n.tran 20p 4n\n.end\n",
        {"temperature": "125"},
        {"temperature": {"target": ".temp"}},
    )

    assert result.success
    assert ".temp 125" in result.text
    assert result.text.index(".temp 125") < result.text.lower().index(".end")


def test_rewrite_spice_parameters_reports_missing_target():
    result = rewrite_spice_parameters(
        "M1 out in vdd vdd PMOS W=1u L=0.15u\n.end\n",
        {"missing": "2u"},
        {"missing": {"target": "M9.W"}},
    )

    assert not result.success
    assert "M9.W" in result.message


def test_sky130_sweep_cli_mock_writes_runs_leaderboard_and_next_space(tmp_path):
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
    output_root = tmp_path / "sky130_sweep"

    env = os.environ.copy()
    env.pop("PDK_ROOT", None)
    env.pop("SKYWATER_PDK_ROOT", None)

    env = os.environ.copy()
    env.pop("PDK_ROOT", None)
    env.pop("SKYWATER_PDK_ROOT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-sweep",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--max-runs",
            "2",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    runs = pd.read_csv(output_root / "sky130_sweep_runs.csv")
    leaderboard = pd.read_csv(output_root / "sky130_sweep_leaderboard.csv")
    sensitivity = pd.read_csv(output_root / "sky130_sweep_sensitivity.csv")
    assert len(runs) == 2
    assert len(leaderboard) == 2
    assert {"m1_width", "load_cap", "overall_score", "status", "run_dir"} <= set(runs.columns)
    assert {"topology_profile", "dc_gain_db", "static_power_w"} <= set(runs.columns)
    assert "topology_profile" in leaderboard.columns
    assert {"parameter", "best_value", "score_delta"} <= set(sensitivity.columns)
    first_run = output_root / runs.loc[0, "run_dir"]
    assert (first_run / "params.yaml").exists()
    assert (first_run / "waveform.csv").exists()
    assert (first_run / "real_summary.json").exists()
    assert (first_run / "score_summary.json").exists()
    assert (first_run / "next_candidates.csv").exists()
    assert (output_root / "next_param_space.yaml").exists()
    params = (first_run / "params.yaml").read_text(encoding="utf-8")
    testbench = (first_run / "testbench.spice").read_text(encoding="utf-8")
    assert "m1_width: 1u" in params
    assert "M1 vout vin vdd vdd PMOS W=1u" in testbench


def test_sky130_sweep_cli_reports_missing_pdk_root_for_real_run(tmp_path):
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

    env = os.environ.copy()
    env.pop("PDK_ROOT", None)
    env.pop("SKYWATER_PDK_ROOT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-sweep",
            "--mock-dataset-json",
            str(rows_path),
            "--sweep",
            str(sweep_path),
            "--output-root",
            str(tmp_path / "sky130_sweep"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 2
    assert "PDK" in result.stderr
