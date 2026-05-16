from goa_eval.scorer import score_real_evaluation


def test_scorer_separates_hard_constraints_soft_scores_and_reasons():
    summary = {
        "Seq_pass": True,
        "All_pulses_exist": True,
        "FalseTriggerCount": 0,
        "Max_overlap_ratio": 0.2,
        "Max_ripple": 0.7,
        "Max_voltage_loss": 0.1,
        "Delay_std": 0.2e-6,
        "Width_std": 0.2e-6,
        "VOH_min": 6.0,
        "high_threshold": 5.0,
        "Width_mean": 10e-6,
    }
    spec = {
        "max_overlap_ratio": 0.1,
        "max_ripple_v": 0.5,
        "max_voltage_loss_v": 0.5,
        "max_delay_std": 0.5e-6,
        "min_voh_margin_v": 1.0,
        "target_pulse_width": 10e-6,
        "pulse_width_tolerance": 1e-6,
        "weights": {
            "function_score": 0.35,
            "quality_score": 0.25,
            "stability_score": 0.15,
            "consistency_score": 0.15,
            "cost_score": 0.10,
        },
    }

    scores = score_real_evaluation(summary, [], spec)

    assert scores["hard_constraint_passed"] is False
    assert "hard_constraints" in scores
    assert "soft_scores" in scores
    assert "failure_reasons" in scores
    assert "warning_reasons" in scores
    assert "score_explanations" in scores
    assert scores["hard_constraints"]["Max_overlap_ratio"]["passed"] is False
    assert scores["hard_constraints"]["Max_overlap_ratio"]["current_value"] == 0.2
    assert scores["hard_constraints"]["Max_overlap_ratio"]["threshold"] == 0.1
    assert any("Max_overlap_ratio" in item for item in scores["failure_reasons"])
    assert "overall_score" in scores
    assert scores["soft_scores"]["stability_score"]["score"] == scores["stability_score"]
    assert scores["score_explanations"]["stability_score"]["deduction"] >= 0.0
