import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

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


def test_cli_propose_candidates_writes_csv_and_markdown(tmp_path):
    summary_path = tmp_path / "real_summary.json"
    score_path = tmp_path / "score_summary.json"
    metrics_path = tmp_path / "real_metrics.csv"
    param_space_path = tmp_path / "param_space.yaml"
    output_csv = tmp_path / "next_candidates.csv"
    output_md = tmp_path / "next_candidates.md"

    summary_path.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "Max_ripple": 1.2,
                "max_ripple_v_limit": 0.5,
                "Delay_mean": 14.0e-6,
                "target_pulse_width": 10.0e-6,
                "pulse_width_tolerance": 1.0e-6,
            }
        ),
        encoding="utf-8",
    )
    score_path.write_text(json.dumps({"hard_constraint_passed": False}), encoding="utf-8")
    pd.DataFrame([{"stage": 1, "node": "o1", "Ripple": 1.2}]).to_csv(metrics_path, index=False)
    param_space_path.write_text(
        """
parameters:
  capacitance:
    unit: F
    values: [8.0e-13, 1.0e-12]
  drive_resistance:
    unit: ohm
    values: [1000, 1500]
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "propose-candidates",
            "--summary",
            str(summary_path),
            "--score",
            str(score_path),
            "--metrics",
            str(metrics_path),
            "--param-space",
            str(param_space_path),
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    table = pd.read_csv(output_csv)
    assert {
        "schema_version",
        "result_version",
        "candidate_id",
        "priority",
        "parameter",
        "direction",
        "candidate_value",
        "candidate_unit",
        "source_recommendation",
        "trigger_metric",
        "data_source",
        "engineering_validity",
        "strategy",
        "candidate_kind",
        "changed_parameters",
        "parameters_json",
        "search_score",
        "rationale",
    } <= set(table.columns)
    assert {"capacitance", "drive_resistance"} <= set(table["parameter"])
    assert "simulation_only" in output_md.read_text(encoding="utf-8")


def test_cli_propose_candidates_rule_strategy_keeps_single_parameter_outputs(tmp_path):
    summary_path = tmp_path / "real_summary.json"
    param_space_path = tmp_path / "param_space.yaml"
    output_csv = tmp_path / "next_candidates.csv"
    output_md = tmp_path / "next_candidates.md"

    summary_path.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "Max_ripple": 1.2,
                "max_ripple_v_limit": 0.5,
            }
        ),
        encoding="utf-8",
    )
    param_space_path.write_text(
        """
parameters:
  capacitance:
    unit: F
    values: [8.0e-13, 1.0e-12]
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "propose-candidates",
            "--strategy",
            "rule",
            "--summary",
            str(summary_path),
            "--param-space",
            str(param_space_path),
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    table = pd.read_csv(output_csv)
    assert set(table["strategy"]) == {"rule"}
    assert set(table["candidate_kind"]) == {"single_parameter"}


def test_cli_propose_candidates_uses_topology_profile_penalties(tmp_path):
    summary_path = tmp_path / "real_summary.json"
    score_path = tmp_path / "score_summary.json"
    metrics_path = tmp_path / "real_metrics.csv"
    param_space_path = tmp_path / "param_space.yaml"
    output_csv = tmp_path / "next_candidates.csv"
    output_md = tmp_path / "next_candidates.md"

    summary_path.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ),
        encoding="utf-8",
    )
    score_path.write_text(
        json.dumps(
            {
                "topology_profile": "ota",
                "analysis_metric_penalties": {
                    "dc_gain_db": {
                        "severity": "fail",
                        "score": 60.0,
                        "deduction": 40.0,
                        "current_value": 24.0,
                        "threshold": 40.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"stage": 1, "node": "o1"}]).to_csv(metrics_path, index=False)
    param_space_path.write_text(
        """
parameters:
  m1_width:
    unit: m
    values: ["1u", "2u"]
  m2_width:
    unit: m
    values: ["1u"]
  load_cap:
    unit: F
    values: ["1pF"]
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "propose-candidates",
            "--summary",
            str(summary_path),
            "--score",
            str(score_path),
            "--metrics",
            str(metrics_path),
            "--param-space",
            str(param_space_path),
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    table = pd.read_csv(output_csv)
    assert list(table.columns[:18]) == [
        "schema_version",
        "result_version",
        "candidate_id",
        "priority",
        "parameter",
        "direction",
        "candidate_value",
        "candidate_unit",
        "source_recommendation",
        "trigger_metric",
        "data_source",
        "engineering_validity",
        "strategy",
        "candidate_kind",
        "changed_parameters",
        "parameters_json",
        "search_score",
        "rationale",
    ]
    assert {"m1_width", "m2_width", "load_cap"} & set(table["parameter"])
    assert all("dc_gain_db" in metric for metric in table["trigger_metric"])
    assert "simulation_only" in output_md.read_text(encoding="utf-8")


def test_cli_propose_candidates_uses_hard_constraint_failures(tmp_path):
    summary_path = tmp_path / "real_summary.json"
    score_path = tmp_path / "score_summary.json"
    param_space_path = tmp_path / "param_space.yaml"
    output_csv = tmp_path / "next_candidates.csv"
    output_md = tmp_path / "next_candidates.md"

    summary_path.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
            }
        ),
        encoding="utf-8",
    )
    score_path.write_text(
        json.dumps(
            {
                "hard_constraint_passed": False,
                "hard_constraints": {
                    "All_pulses_exist": {"passed": False, "current_value": False, "threshold": True},
                    "Seq_pass": {"passed": False, "current_value": False, "threshold": True},
                },
            }
        ),
        encoding="utf-8",
    )
    param_space_path.write_text(
        """
parameters:
  drive_resistance:
    unit: ohm
    values: [1000, 1500]
  transistor_width:
    unit: m
    values: [8.0e-7, 1.0e-6]
  load_cap:
    unit: F
    values: [8.0e-13, 1.0e-12]
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "propose-candidates",
            "--summary",
            str(summary_path),
            "--score",
            str(score_path),
            "--param-space",
            str(param_space_path),
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    table = pd.read_csv(output_csv)
    assert not table.empty
    assert {"All_pulses_exist", "Seq_pass"} & set(table["trigger_metric"])
    assert {"drive_resistance", "transistor_width", "load_cap"} & set(table["parameter"])
    assert set(table["engineering_validity"]) == {"simulation_only"}


def test_cli_analyze_params_writes_mock_deepseek_outputs(tmp_path):
    summary_path = tmp_path / "real_summary.json"
    score_path = tmp_path / "score_summary.json"
    metrics_path = tmp_path / "real_metrics.csv"
    candidates_path = tmp_path / "next_candidates.csv"
    params_path = tmp_path / "params.yaml"
    output_md = tmp_path / "llm_parameter_analysis.md"
    output_json = tmp_path / "llm_parameter_analysis.json"

    summary_path.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "Overall_status": "FAIL",
                "Max_ripple": 1.2,
            }
        ),
        encoding="utf-8",
    )
    score_path.write_text(json.dumps({"hard_constraint_passed": False, "overall_score": 72.5}), encoding="utf-8")
    pd.DataFrame([{"stage": 1, "node": "o1", "Ripple": 1.2}]).to_csv(metrics_path, index=False)
    pd.DataFrame(
        [
            {
                "candidate_id": "cand_001",
                "parameter": "capacitance",
                "direction": "increase",
                "candidate_value": 1.2e-12,
            }
        ]
    ).to_csv(candidates_path, index=False)
    params_path.write_text(
        """
run_id: run_001
parameters:
  capacitance: 1.0e-12
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "analyze-params",
            "--summary",
            str(summary_path),
            "--score",
            str(score_path),
            "--metrics",
            str(metrics_path),
            "--candidates",
            str(candidates_path),
            "--params",
            str(params_path),
            "--mock-response",
            "建议优先复核 cand_001。",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "deepseek-v4-pro" in output_md.read_text(encoding="utf-8")
    assert "simulation_only" in output_md.read_text(encoding="utf-8")
    output = json.loads(output_json.read_text(encoding="utf-8"))
    assert output["model"] == "deepseek-v4-pro"
    assert output["analysis"] == "建议优先复核 cand_001。"
