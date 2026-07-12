import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.sky130_transient import (
    Sky130DependencyError,
    build_output_node_map,
    load_sky130_rows,
    prepare_testbench,
    run_ngspice,
    resolve_ngspice_executable,
    resolve_pdk_library_paths,
    write_netlist_structure_artifacts,
)


def _row() -> dict:
    return {
        "circuit_id": "amp_001",
        "base_circuit_id": "amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": "\n".join(
            [
                ".title amsnet style fixture",
                "M1 vout vin vdd vdd PMOS W=2u L=0.15u",
                "M2 vout vin 0 0 NMOS W=1u L=0.15u",
                "R1 vout vaux 10k",
                "C1 vout 0 2pF",
                "I1 vdd 0 DC 10uA",
                ".MODEL NMOS NMOS (LEVEL=1 VTO=0.7 KP=1e-4)",
                ".MODEL PMOS PMOS (LEVEL=1 VTO=-0.7 KP=1e-4)",
                ".OP",
                ".END",
            ]
        ),
        "testbench_spice": ".title fixture\nV1 vin 0 pulse(0 1.8 1n 1n 1n 5n 20n)\n.tran 1n 40n\n.end\n",
        "netlist_json": {
            "ports": [
                {"name": "vout", "role": "output_v"},
                {"name": "vout_aux", "role": "output_v"},
                {"name": "vin", "role": "input_v"},
            ]
        },
    }


def test_build_output_node_map_finds_output_v_ports():
    assert build_output_node_map(_row()) == {"o1": "vout", "o2": "vout_aux"}


def test_prepare_testbench_writes_artifacts_and_control_block(tmp_path):
    node_map = build_output_node_map(_row())

    prepared = prepare_testbench(_row(), tmp_path, node_map)

    assert prepared.testbench_path.exists()
    assert (tmp_path / "dataset_row.json").exists()
    assert json.loads((tmp_path / "node_map.json").read_text(encoding="utf-8")) == node_map
    text = prepared.testbench_path.read_text(encoding="utf-8")
    assert "wrdata" in text
    assert "v(vout)" in text
    assert "v(vout_aux)" in text


def test_prepare_testbench_expands_local_sky130_library_path(tmp_path, monkeypatch):
    pdk = tmp_path / "pdk"
    library = pdk / "libs.tech" / "ngspice" / "sky130.lib.spice"
    library.parent.mkdir(parents=True)
    library.write_text("* pdk lib\n", encoding="utf-8")
    monkeypatch.setenv("PDK_ROOT", str(pdk))
    row = {**_row(), "testbench_spice": '.lib "sky130.lib.spice" tt\n.end\n'}

    prepared = prepare_testbench(row, tmp_path / "run", build_output_node_map(row))

    text = prepared.testbench_path.read_text(encoding="utf-8")
    generated_library = tmp_path / "run" / "sky130_minimal.lib.spice"
    assert '.lib "sky130_minimal.lib.spice" tt' in text
    assert generated_library.exists()
    assert library.parent.as_posix() in generated_library.read_text(encoding="ascii")


def test_resolve_pdk_library_paths_leaves_unknown_libraries_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("PDK_ROOT", str(tmp_path / "missing"))

    assert resolve_pdk_library_paths('.lib "custom.lib" tt\n') == '.lib "custom.lib" tt\n'


def test_write_netlist_structure_artifacts_uses_source_netlist(tmp_path):
    structure = write_netlist_structure_artifacts(_row(), tmp_path)

    assert structure["structure_status"] == "generated"
    assert structure["source_netlist_field"] == "spice_netlist"
    assert (tmp_path / "source_netlist.spice").exists()
    data = json.loads((tmp_path / "netlist_structure.json").read_text(encoding="utf-8"))
    assert data["scalar_features"]["mos_count"] == 2
    assert data["scalar_features"]["resistor_count"] == 1
    assert data["scalar_features"]["current_source_count"] == 1


def test_write_netlist_structure_artifacts_can_be_skipped(tmp_path):
    structure = write_netlist_structure_artifacts(_row(), tmp_path, skip=True)

    assert structure["structure_status"] == "skipped"
    assert not (tmp_path / "source_netlist.spice").exists()


def test_run_ngspice_reports_missing_binary(tmp_path):
    prepared = prepare_testbench(_row(), tmp_path, build_output_node_map(_row()))

    with pytest.raises(Sky130DependencyError, match="ngspice"):
        run_ngspice(prepared, ngspice_cmd="definitely_missing_ngspice")


def test_resolve_ngspice_executable_prefers_windows_console_binary(tmp_path, monkeypatch):
    executable = tmp_path / "ngspice.exe"
    executable.write_text("", encoding="utf-8")
    console = tmp_path / "ngspice_con.exe"
    console.write_text("", encoding="utf-8")
    monkeypatch.setattr("goa_eval.sky130_transient.shutil.which", lambda _: str(executable))

    resolved = resolve_ngspice_executable("ngspice")

    assert Path(resolved).name == "ngspice_con.exe"


def test_load_sky130_rows_filters_mock_rows_by_topology_and_source(tmp_path):
    rows = [
        {**_row(), "circuit_id": "keep", "topology": "ota", "source_dataset": "alpha"},
        {**_row(), "circuit_id": "drop_topology", "topology": "vco", "source_dataset": "alpha"},
        {**_row(), "circuit_id": "drop_source", "topology": "ota", "source_dataset": "beta"},
    ]
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps(rows), encoding="utf-8")

    selected = load_sky130_rows(
        split="train",
        max_rows=5,
        topology="ota",
        source_dataset="alpha",
        dataset_name="unused",
        mock_dataset_json=rows_path,
    )

    assert [row["circuit_id"] for row in selected] == ["keep"]


def test_load_sky130_rows_uses_local_external_fixture_without_datasets():
    selected = load_sky130_rows(
        split="train",
        max_rows=1,
        topology=None,
        source_dataset="local_external_ngspice",
        dataset_name="unused",
        mock_dataset_json=None,
    )

    assert [row["circuit_id"] for row in selected] == ["sky130_candidate_chain"]
    assert selected[0]["source_dataset"] == "local_external_ngspice"
    assert len(build_output_node_map(selected[0])) >= 3


def test_sky130_transient_cli_mock_writes_small_closed_loop(tmp_path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    output_root = tmp_path / "sky130"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-transient",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--max-rows",
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
    summary = pd.read_csv(output_root / "sky130_runs.csv")
    run_dir = output_root / summary.loc[0, "run_dir"]
    assert summary.loc[0, "status"] == "evaluated"
    assert summary.loc[0, "structure_status"] == "generated"
    assert summary.loc[0, "mos_count"] == 2
    assert summary.loc[0, "resistor_count"] == 1
    assert (run_dir / "waveform.csv").exists()
    assert (run_dir / "source_netlist.spice").exists()
    assert (run_dir / "netlist_structure.json").exists()
    assert (run_dir / "real_summary.json").exists()
    assert (run_dir / "score_summary.json").exists()
    assert (run_dir / "optimization_dataset.csv").exists()
    assert (run_dir / "next_candidates.csv").exists()
    status = json.loads((run_dir / "sky130_status.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "sky130_metadata.json").read_text(encoding="utf-8"))
    assert status["engineering_validity"] == "simulation_only"
    assert metadata["structure_scalar_features"]["mos_count"] == 2


def test_sky130_transient_cli_reports_missing_datasets_dependency(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-transient",
            "--mock-ngspice",
            "--max-rows",
            "1",
            "--output-root",
            str(tmp_path / "sky130"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "datasets" in result.stderr
    assert "sky130" in result.stderr


def test_sky130_transient_cli_reports_missing_ngspice_dependency(tmp_path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "sky130-transient",
            "--mock-dataset-json",
            str(rows_path),
            "--ngspice-cmd",
            "definitely_missing_ngspice",
            "--max-rows",
            "1",
            "--output-root",
            str(tmp_path / "sky130"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "ngspice" in result.stderr
