import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import write_extracted_fixture, write_raw_fixture


def assert_is_version_marker(value: str) -> None:
    assert value == "unknown" or re.fullmatch(r"[0-9a-f]{7,40}", value)


def test_cli_all_writes_core_outputs(tmp_path):
    out = tmp_path / "test_run"
    raw = write_raw_fixture(tmp_path / "raw")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "all",
            "--raw",
            str(raw),
            "--mock-waveform",
            "--out",
            str(out),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (out / "metrics" / "metrics.csv").exists()
    assert (out / "metrics" / "netlist_parse.json").exists()
    assert (out / "summary.json").exists()
    assert (out / "run_manifest.json").exists()
    assert (out / "report.md").exists()
    assert (out / "figures" / "v1_v8_comparison.png").stat().st_size > 0

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["data_source"] == "mock"
    assert summary["engineering_validity"] == "workflow_test_only"

    netlists = json.loads((out / "metrics" / "netlist_parse.json").read_text(encoding="utf-8"))
    v8 = next(item for item in netlists if item["name"] == "v8")
    xs1 = next(device for device in v8["devices"] if device["name"] == "Xs1")

    assert {"devices", "subckts", "warnings", "cascade_chain"} <= set(v8)
    assert {"raw_line", "kind", "model", "params_raw", "params_si", "port_map"} <= set(xs1)
    assert "type" not in xs1
    assert xs1["kind"] == "subckt_instance"
    assert xs1["model"] == "sub_1_8T1C"
    assert xs1["port_map"]["output"] == "o1"
    assert v8["cascade_chain"] == ["o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8"]
    assert "sub_1_8T1C" in v8["subckts"]

    report_lines = (out / "report.md").read_text(encoding="utf-8").splitlines()
    assert report_lines[:2] == [
        "This report is generated from mock waveform data for workflow validation only.",
        "It must not be interpreted as a real circuit performance conclusion.",
    ]

    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    required = {
        "run_id",
        "run_time",
        "input_design_path",
        "input_file_hashes",
        "config",
        "thresholds",
        "command",
        "code_version_or_git_commit",
        "data_source",
        "engineering_validity",
    }
    assert required <= set(manifest)
    assert manifest["data_source"] == "mock"
    assert manifest["engineering_validity"] == "workflow_test_only"
    assert_is_version_marker(manifest["code_version_or_git_commit"])


def test_cli_evaluate_design_writes_flat_acceptance_outputs(tmp_path):
    out = tmp_path / "outputs"
    extracted = write_extracted_fixture(tmp_path / "extracted")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "evaluate",
            "--design",
            str(extracted / "v8"),
            "--mock-waveform",
            "--out",
            str(out),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (out / "metrics.csv").exists()
    assert (out / "summary.json").exists()
    assert (out / "report.md").exists()
    assert (out / "run_manifest.json").exists()
    assert (out / "figures" / "v1_v8_comparison.png").stat().st_size > 0

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["data_source"] == "mock"
    assert summary["engineering_validity"] == "workflow_test_only"

    report_lines = (out / "report.md").read_text(encoding="utf-8").splitlines()
    assert report_lines[:2] == [
        "This report is generated from mock waveform data for workflow validation only.",
        "It must not be interpreted as a real circuit performance conclusion.",
    ]

    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    required = {
        "run_id",
        "run_time",
        "input_design_path",
        "input_file_hashes",
        "config",
        "thresholds",
        "command",
        "code_version_or_git_commit",
        "data_source",
        "engineering_validity",
    }
    assert required <= set(manifest)
    assert manifest["input_design_path"].endswith("v8")
    assert manifest["input_file_hashes"]
    assert manifest["config"]["project"]["name"] == "goa_eval_framework"
    assert manifest["thresholds"]["mock"]["data_source"] == "mock"
    assert manifest["command"].startswith("python -m goa_eval.cli evaluate")
    assert_is_version_marker(manifest["code_version_or_git_commit"])
    assert manifest["data_source"] == "mock"
    assert manifest["engineering_validity"] == "workflow_test_only"


def test_cli_parse_accepts_flat_alps_design_with_map_suffix(tmp_path):
    fixture_root = write_extracted_fixture(tmp_path / "extracted")
    extracted = tmp_path / "alps_flat"
    shutil.copytree(fixture_root / "v8", extracted)
    out = tmp_path / "parse_out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "parse",
            "--input",
            str(extracted),
            "--out",
            str(out),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((out / "metrics" / "design_summary.json").read_text(encoding="utf-8"))
    assert len(summary) == 1
    assert summary[0]["name"] == "v8"
    assert summary[0]["mapping_record_count"] == 53
    assert summary[0]["cascade_chain"] == ["o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8"]


def test_cli_evaluate_design_with_waveform_csv_marks_simulation(tmp_path):
    out = tmp_path / "simulation_out"
    extracted = write_extracted_fixture(tmp_path / "extracted")
    waveform = tmp_path / "sample_waveform.csv"
    waveform.write_text(
        "\n".join(
            [
                "XVAL,v(o1),v(o2),v(o3),v(o4),v(o5),v(o6),v(o7),v(o8)",
                "0.0,0,0,0,0,0,0,0,0",
                "0.000001,6,0,0,0,0,0,0,0",
                "0.000002,6,6,0,0,0,0,0,0",
                "0.000003,0,6,6,0,0,0,0,0",
                "0.000004,0,0,6,6,0,0,0,0",
                "0.000005,0,0,0,6,6,0,0,0",
                "0.000006,0,0,0,0,6,6,0,0",
                "0.000007,0,0,0,0,0,6,6,0",
                "0.000008,0,0,0,0,0,0,6,6",
                "0.000009,0,0,0,0,0,0,0,6",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "evaluate",
            "--design",
            str(extracted / "v8"),
            "--waveform-csv",
            str(waveform),
            "--out",
            str(out),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    metrics_text = (out / "metrics.csv").read_text(encoding="utf-8-sig")
    report_text = (out / "report.md").read_text(encoding="utf-8")

    assert summary["data_source"] == "simulation"
    assert summary["engineering_validity"] == "simulation_result"
    assert manifest["data_source"] == "simulation"
    assert manifest["engineering_validity"] == "simulation_result"
    assert "simulation_result" in metrics_text
    assert "simulation waveform data" in report_text
    assert "mock waveform data" not in report_text.splitlines()[0]
