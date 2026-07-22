from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.critic import run_critic_checks


def test_critic_detects_missing_files_and_boundary_mismatch(tmp_path):
    bad_summary = tmp_path / "bad_summary.json"
    bad_summary.write_text(
        '{"data_source":"mock","engineering_validity":"silicon_validated"}',
        encoding="utf-8",
    )
    state = {
        "profile": "unknown",
        "selected_domain_agent": "unsupported",
        "generated_files": {"missing": str(tmp_path / "missing.json"), "bad": str(bad_summary)},
        "tool_results": {},
        "handoff_records": [],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdicts = run_critic_checks(state)
    issues = [issue for verdict in verdicts for issue in verdict.issues]

    assert any("missing output file" in issue for issue in issues)
    assert any("data_source" in issue for issue in issues)
    assert any("unsupported profile" in issue for issue in issues)
    assert any("handoff record missing" in issue for issue in issues)


def test_critic_detects_metric_bad_cells_and_candidate_risk(tmp_path):
    metrics = tmp_path / "metrics.csv"
    pd.DataFrame(
        [
            {"schema_version": "1.0", "result_version": "1.0", "stage": 1, "Ripple": None},
            {"schema_version": "1.0", "result_version": "1.0", "stage": 2, "Ripple": "not_evaluable"},
        ]
    ).to_csv(metrics, index=False)
    candidates = tmp_path / "next_candidates.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "cand_001",
                "parameter": "drive_resistance",
                "candidate_values": "[999999]",
                "parameter_change_count": 3,
            }
        ]
    ).to_csv(candidates, index=False)
    param_space = tmp_path / "params.yaml"
    param_space.write_text("parameters:\n  drive_resistance:\n    values: [1000, 1500]\n", encoding="utf-8")
    state = {
        "generated_files": {"metrics": str(metrics), "next_candidates": str(candidates)},
        "inputs": {"param_space": str(param_space)},
        "candidate_summary": {"candidate_count": 1},
        "tool_results": {
            "RouterAgent": [{"tool_name": "generate_candidates"}],
        },
        "handoff_records": [{"from_agent": "RouterAgent", "to_agent": "CriticAgent"}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdicts = run_critic_checks(state)
    issues = [issue for verdict in verdicts for issue in verdict.issues]

    assert any("bad metric cell" in issue for issue in issues)
    assert any("parameter change count" in issue for issue in issues)
    assert any("unauthorized tool" in issue for issue in issues)


def test_critic_detects_domain_risks_and_incomplete_netlist(tmp_path):
    incomplete_netlist = tmp_path / "incomplete.sp"
    incomplete_netlist.write_text(
        "\n".join(
            [
                "* Missing .END and .ENDS",
                ".SUBCKT inv in out vdd vss",
                "R1 out vss 1k",
            ]
        ),
        encoding="utf-8",
    )
    state = {
        "score_summary": {
            "hard_constraint_passed": False,
            "hard_constraint_failures": ["Max_overlap_ratio above target"],
        },
        "metrics_summary": {
            "bad_cell_count": 1,
            "metric_stats": {
                "FalseTriggerCount": {"max": 1},
                "OverlapRatio": {"max": 0.31},
            },
        },
        "inputs": {"netlist": str(incomplete_netlist)},
        "netlist_summary": {"not_implemented_yet": False},
        "tool_results": {},
        "handoff_records": [{"from_agent": "NetlistAgent", "to_agent": "CriticAgent"}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdicts = run_critic_checks(state)
    issues = [issue for verdict in verdicts for issue in verdict.issues]

    assert any("hard_constraint_failed" in issue for issue in issues)
    assert any("FalseTriggerCount" in issue for issue in issues)
    assert any("OverlapRatio" in issue for issue in issues)
    assert any("netlist missing .END" in issue for issue in issues)
    assert any(".SUBCKT without matching .ENDS" in issue for issue in issues)
    assert any("netlist missing MOS devices" in issue for issue in issues)


def test_critic_verdict_contains_severity_and_risk_type():
    state = {
        "score_summary": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "hard_constraint_passed": False,
            "hard_constraint_failures": ["Max_overlap_ratio above target"],
        },
        "metrics_summary": {
            "bad_cell_count": 1,
            "bad_cell_values": ["not_evaluable"],
            "metric_stats": {
                "FalseTriggerCount": {"max": 1},
                "OverlapRatio": {"max": 0.31},
            },
        },
        "tool_results": {"RouterAgent": [{"tool_name": "generate_candidates"}]},
        "handoff_records": [{"from_agent": "RouterAgent", "to_agent": "CriticAgent"}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdict = run_critic_checks(state)[0].to_dict()

    assert verdict["verdict"] == "reject"
    assert verdict["severity"] == "critical"
    assert verdict["risk_type"] == "hard_constraint"
    risk_types = {risk["risk_type"] for risk in verdict["risks"]}
    assert {"hard_constraint", "not_evaluable", "false_trigger", "overlap", "tool_permission"} <= risk_types


def test_critic_checks_current_main_artifact_risks(tmp_path):
    real_summary = tmp_path / "real_summary.json"
    real_summary.write_text(
        """
{
  "data_source": "real_simulation_csv",
  "engineering_validity": "simulation_only",
  "FalseTriggerCount": 1,
  "Max_overlap_ratio": 0.33,
  "Max_ripple": 0.8,
  "max_ripple_v_limit": 0.5,
  "LowFreqStable": "not_evaluable_with_current_waveform"
}
""".strip(),
        encoding="utf-8",
    )
    score_summary = tmp_path / "score_summary.json"
    score_summary.write_text(
        """
{
  "data_source": "real_simulation_csv",
  "engineering_validity": "simulation_only",
  "hard_constraint_passed": false,
  "not_evaluable_metrics": ["dc_gain_db"],
  "analysis_metric_penalties": {"dc_gain_db": "not_evaluable"}
}
""".strip(),
        encoding="utf-8",
    )
    validation = tmp_path / "validation_summary.csv"
    validation.write_text("target.status\nfailed\n", encoding="utf-8")
    report = tmp_path / "diagnosis_report.md"
    report.write_text("This is physical validation.", encoding="utf-8")
    candidates = tmp_path / "next_candidates.csv"
    candidates.write_text("candidate_id,parameter,candidate_values\ncand_001,load_cap,[1p]\n", encoding="utf-8")
    param_space = tmp_path / "params.yaml"
    param_space.write_text("parameters:\n  load_cap:\n    values: [1p]\n", encoding="utf-8")

    state = {
        "inputs": {
            "artifact_dir": str(tmp_path),
            "param_space": str(param_space),
        },
        "tool_results": {},
        "handoff_records": [{"from_agent": "GOAAgent", "to_agent": "CriticAgent"}],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }

    verdict = run_critic_checks(state)[0].to_dict()
    issues = verdict["issues"]
    risk_types = {risk["risk_type"] for risk in verdict["risks"]}

    assert any("FalseTriggerCount" in issue for issue in issues)
    assert any("Max_overlap_ratio" in issue for issue in issues)
    assert any("profile metric missingness" in issue for issue in issues)
    assert any("validation target status" in issue for issue in issues)
    assert any("forbidden phrase" in issue for issue in issues)
    assert {"false_trigger", "overlap", "profile_metric_missingness", "validation_target_status", "physical_validation_claim"} <= risk_types
