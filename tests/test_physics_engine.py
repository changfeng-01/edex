import builtins
import subprocess

import pandas as pd

from goa_eval.physics_engine import evaluate_candidate_physics, rank_physics_guided_points


def test_larger_transistor_width_improves_drive_and_reduces_rc_proxy():
    narrow = evaluate_candidate_physics({"m1_width": "1u", "load_cap": "1pF"})
    wide = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF"})

    assert wide.proxy_metrics["drive_to_load_ratio"] > narrow.proxy_metrics["drive_to_load_ratio"]
    assert wide.proxy_metrics["rc_delay_s"] < narrow.proxy_metrics["rc_delay_s"]


def test_larger_load_cap_reduces_drive_and_increases_rc_proxy():
    light_load = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF"})
    heavy_load = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "2pF"})

    assert heavy_load.proxy_metrics["drive_to_load_ratio"] < light_load.proxy_metrics["drive_to_load_ratio"]
    assert heavy_load.proxy_metrics["rc_delay_s"] > light_load.proxy_metrics["rc_delay_s"]


def test_timing_spacing_below_two_rc_is_hard_violation():
    result = evaluate_candidate_physics(
        {
            "m1_width": "1u",
            "load_cap": "1pF",
            "phase_a_delay": "0",
            "phase_b_delay": "1u",
        }
    )

    assert result.proxy_metrics["timing_spacing_over_rc"] < 2
    assert "timing_spacing_below_2x_rc_delay" in result.violations
    assert result.physical_hard_passed is False


def test_pulse_width_below_three_rc_is_hard_violation():
    result = evaluate_candidate_physics(
        {
            "m1_width": "1u",
            "load_cap": "1pF",
            "gate_pulse_width": "2u",
        }
    )

    assert result.proxy_metrics["pulse_width_over_rc"] < 3
    assert "pulse_width_below_3x_rc_delay" in result.violations
    assert result.physical_hard_passed is False


def test_vdd_at_or_below_threshold_is_hard_violation():
    result = evaluate_candidate_physics({"vdd": "1.0", "vth": "1.0"})

    assert result.proxy_metrics["voltage_margin_v"] == 0
    assert "non_positive_voltage_margin" in result.violations
    assert result.physical_hard_passed is False


def test_rank_physics_guided_points_returns_physics_prior_metadata():
    points = [
        {"m1_width": "1u", "load_cap": "2pF"},
        {"m1_width": "3u", "load_cap": "1pF"},
    ]
    history = pd.DataFrame([{"overall_score": 75.0, "m1_width": "1u", "load_cap": "1pF"}])

    ranked = rank_physics_guided_points(points, history=history, max_points=1)

    assert len(ranked) == 1
    _, metadata = ranked[0]
    assert metadata["candidate_source"] == "physics_prior_engine"
    assert metadata["optimizer_strategy"] == "physics_guided_hybrid"
    for key in [
        "physics_score",
        "physical_hard_passed",
        "physics_proxy_json",
        "physics_violations",
        "model_status",
    ]:
        assert key in metadata


def test_rank_physics_guided_points_prefers_stronger_drive_under_same_load():
    points = [
        {"m1_width": "1u", "load_cap": "1pF"},
        {"m1_width": "3u", "load_cap": "1pF"},
    ]
    history = pd.DataFrame([{"overall_score": 75.0, "m1_width": "1u", "load_cap": "1pF"}])

    ranked = rank_physics_guided_points(points, history=history)

    assert ranked[0][0]["m1_width"] == "3u"
    assert ranked[0][1]["physics_score"] > ranked[1][1]["physics_score"]
    assert "drive/load proxy improves versus baseline" in ranked[0][1]["source_candidate_rationale"]


def test_heavier_load_gets_mask_penalty_and_specific_rationale():
    baseline = {"m1_width": "2u", "load_cap": "1pF"}

    nominal = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF"}, baseline=baseline)
    heavy = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "3pF"}, baseline=baseline)

    assert heavy.physics_score < nominal.physics_score
    assert "rc_delay_proxy_degraded_vs_baseline" in heavy.violations
    assert "drive_load_proxy_weaker_than_baseline" in heavy.violations
    assert "mask penalty: RC delay degraded versus baseline" in heavy.rationale
    assert "mask penalty: drive/load ratio weakened versus baseline" in heavy.rationale


def test_low_voltage_margin_has_specific_mask_penalty_rationale():
    result = evaluate_candidate_physics({"vdd": "0.85", "vth": "0.75"})

    assert "low_voltage_margin" in result.violations
    assert "mask penalty: voltage margin is low" in result.rationale


def test_evaluate_candidate_physics_does_not_run_an_external_simulator_or_read_files(monkeypatch):
    def fail_open(*args, **kwargs):
        raise AssertionError("physics prior must not read external files")

    def fail_subprocess(*args, **kwargs):
        raise AssertionError("physics prior must not run external commands")

    monkeypatch.setattr(builtins, "open", fail_open)
    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    result = evaluate_candidate_physics({"m1_width": "2u", "load_cap": "1pF", "vdd": "1.8", "vth": "0.7"})

    assert result.model_status == "physics_prior_engine_v1"
    assert result.physics_score > 0
