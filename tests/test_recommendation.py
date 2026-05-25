import json
from pathlib import Path

import pandas as pd

from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


def _summary() -> dict:
    return {
        "schema_version": "1.0",
        "result_version": "1.0",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "Max_overlap_ratio": 0.22,
        "max_overlap_ratio_limit": 0.10,
        "Max_ripple": 5.4,
        "max_ripple_v_limit": 0.5,
        "Delay_mean": 14.0e-6,
        "target_pulse_width": 10.0e-6,
        "FalseTriggerCount": 2,
        "LowFreqStable": "not_evaluable_with_current_waveform",
        "Overall_status": "FAIL_OVERLAP",
    }


def test_build_recommendations_covers_core_rule_failures():
    recommendations = build_recommendations(_summary(), {"hard_constraint_passed": False}, pd.DataFrame())
    text = "\n".join(item["message"] for item in recommendations)

    assert any(item["recommendation_id"] == "overlap_timing_review" for item in recommendations)
    overlap = next(item for item in recommendations if item["recommendation_id"] == "overlap_timing_review")
    assert overlap["trigger_metric"] == "Max_overlap_ratio"
    assert overlap["current_value"] == 0.22
    assert overlap["threshold"] == 0.10
    assert "相邻级" in overlap["possible_physical_causes"]
    assert "缩短导通窗口" in overlap["next_tuning_actions"]
    assert overlap["needs_metric_review"] is True
    assert "相邻级时序" in text
    assert "hold window" in text
    assert "驱动能力" in text
    assert "非选通节点异常高电平" in text
    assert "完整帧周期" in text
    assert all(item["engineering_validity"] == "simulation_only" for item in recommendations)


def test_build_recommendations_carries_metric_penalty_context_from_score():
    score = {
        "hard_constraint_passed": False,
        "metric_penalties": {
            "Max_overlap_ratio": {
                "severity": "critical",
                "score": 8.4,
                "deduction": 91.6,
            }
        },
    }

    recommendations = build_recommendations(_summary(), score, pd.DataFrame())
    overlap = next(item for item in recommendations if item["trigger_metric"] == "Max_overlap_ratio")

    assert overlap["metric_penalty_severity"] == "critical"
    assert overlap["metric_penalty_score"] == 8.4
    assert overlap["metric_penalty_deduction"] == 91.6


def test_build_recommendations_adds_topology_specific_analysis_guidance():
    score = {
        "topology_profile": "ota",
        "analysis_metric_penalties": {
            "dc_gain_db": {
                "severity": "fail",
                "score": 75.0,
                "deduction": 25.0,
                "current_value": 30.0,
                "threshold": 40.0,
            },
            "static_power_w": {
                "severity": "critical",
                "score": 0.0,
                "deduction": 100.0,
                "current_value": 0.02,
                "threshold": 0.01,
            },
        },
    }

    recommendations = build_recommendations(
        {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        },
        score,
        pd.DataFrame(),
    )
    ids = {item["recommendation_id"] for item in recommendations}
    gain = next(item for item in recommendations if item["trigger_metric"] == "dc_gain_db")

    assert "ota_gain_bandwidth_review" in ids
    assert "ota_power_bias_review" in ids
    assert "no_rule_failure_detected" not in ids
    assert gain["topology_profile"] == "ota"
    assert gain["metric_penalty_severity"] == "fail"
    assert gain["metric_penalty_deduction"] == 25.0
    assert all(item["engineering_validity"] == "simulation_only" for item in recommendations)


def test_build_recommendations_adds_hard_constraint_failure_guidance():
    score = {
        "hard_constraint_passed": False,
        "hard_constraints": {
            "All_pulses_exist": {"passed": False, "current_value": False, "threshold": True},
            "Seq_pass": {"passed": False, "current_value": False, "threshold": True},
        },
    }

    recommendations = build_recommendations(
        {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        },
        score,
        pd.DataFrame(),
    )
    by_metric = {item["trigger_metric"]: item for item in recommendations}

    assert "All_pulses_exist" in by_metric
    assert "Seq_pass" in by_metric
    assert by_metric["All_pulses_exist"]["recommendation_id"] == "missing_pulse_recovery_review"
    assert by_metric["Seq_pass"]["recommendation_id"] == "sequence_order_recovery_review"
    assert by_metric["All_pulses_exist"]["current_value"] is False
    assert by_metric["Seq_pass"]["threshold"] is True
    assert "no_rule_failure_detected" not in {item["recommendation_id"] for item in recommendations}
    assert all(item["engineering_validity"] == "simulation_only" for item in recommendations)


def test_write_recommendations_markdown_keeps_simulation_only_boundary(tmp_path: Path):
    summary_path = tmp_path / "real_summary.json"
    score_path = tmp_path / "score_summary.json"
    metrics_path = tmp_path / "real_metrics.csv"
    output_path = tmp_path / "recommendations.md"
    summary_path.write_text(json.dumps(_summary()), encoding="utf-8")
    score_path.write_text(json.dumps({"hard_constraint_passed": False}), encoding="utf-8")
    pd.DataFrame([{"stage": 1, "node": "o1", "Ripple": 5.4}]).to_csv(metrics_path, index=False)

    write_recommendations_markdown(
        summary_path=summary_path,
        score_path=score_path,
        metrics_path=metrics_path,
        output_path=output_path,
    )

    content = output_path.read_text(encoding="utf-8")
    assert "simulation_only" in content
    assert "不是实物测试结果" in content
    assert "overlap_timing_review" in content
    assert "trigger_metric" in content
    assert "possible_physical_causes" in content
    assert "next_tuning_actions" in content
    assert "自动完成电路优化" not in content
