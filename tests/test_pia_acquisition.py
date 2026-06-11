from __future__ import annotations

from goa_eval.pia_ca_llso.acquisition import compute_acquisition_score, explain_acquisition


def test_acquisition_score_is_bounded_and_explainable() -> None:
    row = {
        "p_l1": 0.9,
        "predicted_score": 80,
        "p_hard_pass": 0.8,
        "uncertainty": 0.2,
        "attention_l1_mass": 0.7,
        "physics_distance_to_l1": 0.1,
        "diversity_score": 0.5,
    }

    score, components = compute_acquisition_score(row)

    assert 0 <= score <= 1
    assert components["diagnostic_status"] == "ok"
    assert "p_l1" in explain_acquisition({**row, "acquisition_score": score})
