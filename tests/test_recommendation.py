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
