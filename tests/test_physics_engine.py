import pandas as pd

from goa_eval.physics_engine import evaluate_candidate_physics, rank_physics_guided_points


def test_wider_transistor_improves_drive_proxy_and_lowers_tau():
    narrow = evaluate_candidate_physics({"m1_width": "1u", "load_cap": "1pF"})
    wide = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF"})

    assert wide.proxy_metrics["drive_to_load_ratio"] > narrow.proxy_metrics["drive_to_load_ratio"]
    assert wide.proxy_metrics["rc_delay_proxy"] < narrow.proxy_metrics["rc_delay_proxy"]


def test_larger_load_cap_worsens_drive_proxy_and_increases_tau():
    small_load = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF"})
    large_load = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "2pF"})

    assert large_load.proxy_metrics["drive_to_load_ratio"] < small_load.proxy_metrics["drive_to_load_ratio"]
    assert large_load.proxy_metrics["rc_delay_proxy"] > small_load.proxy_metrics["rc_delay_proxy"]


def test_timing_spacing_below_two_rc_is_hard_violation():
    result = evaluate_candidate_physics(
        {
            "R_driver": "1kohm",
            "load_cap": "1pF",
            "pulse_delay": "1ns",
            "pulse_width": "5ns",
        }
    )

    assert result.physical_hard_passed is False
    assert "timing_spacing_over_rc < 2" in result.violations


def test_pulse_width_below_three_rc_is_hard_violation():
    result = evaluate_candidate_physics(
        {
            "R_driver": "1kohm",
            "load_cap": "1pF",
            "pulse_delay": "4ns",
            "pulse_width": "2ns",
        }
    )

    assert result.physical_hard_passed is False
    assert "pulse_width_over_rc < 3" in result.violations


def test_vdd_below_threshold_is_hard_violation():
    result = evaluate_candidate_physics(
        {
            "m1_width": "2u",
            "load_cap": "1pF",
            "VDD": "0.4V",
            "Vth": "0.5V",
        }
    )

    assert result.physical_hard_passed is False
    assert "voltage_margin <= 0" in result.violations


def test_physics_ranking_prefers_hard_passing_higher_score_points():
    points = [
        {
            "R_driver": "1kohm",
            "load_cap": "1pF",
            "pulse_delay": "1ns",
            "pulse_width": "2ns",
            "VDD": "1.8V",
            "Vth": "0.5V",
        },
        {
            "R_driver": "1kohm",
            "load_cap": "1pF",
            "pulse_delay": "4ns",
            "pulse_width": "5ns",
            "VDD": "1.8V",
            "Vth": "0.5V",
        },
    ]

    ranked = rank_physics_guided_points(points, history=pd.DataFrame(), max_points=2)

    assert ranked[0][0]["pulse_delay"] == "4ns"
    assert ranked[0][1]["candidate_source"] == "physics_prior_engine"
    assert ranked[0][1]["physical_hard_passed"] is True
    assert ranked[0][1]["physics_score"] > ranked[1][1]["physics_score"]
