from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.physics_distance import (
    _exponential_penalty,
    _linear_penalty,
    _quadratic_penalty,
    compute_capm_distance,
    compute_physics_distance,
    constraint_barrier_score,
    distance_to_l1_physics,
    normalize_distance,
    physics_geodesic_distance_to_l1,
    physics_distance_matrix,
)


def test_physics_distance_computes_weighted_distance_and_matrix() -> None:
    assert compute_physics_distance({"a": 1, "b": 2}, {"a": 4, "b": 6}, {"a": 1, "b": 0.25}) == 13**0.5
    candidates = pd.DataFrame([{"a": 1.0, "b": 2.0}])
    history = pd.DataFrame([{"a": 2.0, "b": 2.0}, {"a": 3.0, "b": 2.0}])
    matrix = physics_distance_matrix(candidates, history)
    assert matrix.shape == (1, 2)
    assert distance_to_l1_physics(candidates.iloc[0], history)["status"] == "ok"
    assert normalize_distance([2, 4]).tolist() == [0.0, 1.0]


def test_normalize_distance_handles_all_infinite_values_without_warning() -> None:
    assert normalize_distance([float("inf"), float("inf")]).tolist() == [0.0, 0.0]


def test_capm_distance_adds_constraint_barrier_and_missing_feature_penalty() -> None:
    safe = {
        "cboot_cload_ratio": 1.2,
        "pullup_pulldown_ratio": 1.0,
        "ron_pullup_cload_proxy": 0.4,
        "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.5,
        "vgl_off_margin": 2.0,
        "clk_slew_proxy": 0.5,
    }
    risky = {**safe, "vgh_vth_margin": 0.1, "ron_pullup_cload_proxy": 3.0}
    incomplete = {key: value for key, value in safe.items() if key != "vgh_vth_margin"}

    assert constraint_barrier_score(risky) > constraint_barrier_score(safe)
    risky_distance = compute_capm_distance(risky, safe)
    safe_distance = compute_capm_distance({**safe, "clk_slew_proxy": 0.55}, safe)
    missing_distance = compute_capm_distance(incomplete, safe)

    assert risky_distance["status"] == "ok"
    assert risky_distance["barrier_cost"] > safe_distance["barrier_cost"]
    assert risky_distance["distance"] > safe_distance["distance"]
    assert missing_distance["missing_penalty"] > 0


def test_capm_geodesic_distance_prefers_low_barrier_path_to_l1() -> None:
    history = pd.DataFrame(
        [
            {
                "sample_id": "l1",
                "level_label": "L1",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 0.4,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 2.5,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
            {
                "sample_id": "bad",
                "level_label": "L4",
                "cboot_cload_ratio": 1.2,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 3.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 0.05,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "safe",
                "cboot_cload_ratio": 1.1,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 0.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 2.3,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
            {
                "candidate_id": "risky",
                "cboot_cload_ratio": 1.1,
                "pullup_pulldown_ratio": 1.0,
                "ron_pullup_cload_proxy": 3.5,
                "ron_pulldown_cload_proxy": 0.4,
                "vgh_vth_margin": 0.05,
                "vgl_off_margin": 2.0,
                "clk_slew_proxy": 0.5,
            },
        ]
    )

    scored = physics_geodesic_distance_to_l1(candidates, history)

    assert list(scored["candidate_id"]) == ["safe", "risky"]
    assert scored.loc[0, "capm_geodesic_distance_to_l1"] < scored.loc[1, "capm_geodesic_distance_to_l1"]
    assert scored.loc[1, "capm_barrier_score"] > scored.loc[0, "capm_barrier_score"]


def test_coupling_extension_with_eight_pairs() -> None:
    safe = {
        "cboot_cload_ratio": 1.2,
        "pullup_pulldown_ratio": 1.0,
        "ron_pullup_cload_proxy": 0.4,
        "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.5,
        "vgl_off_margin": 2.0,
        "clk_slew_proxy": 0.5,
        "holding_droop_proxy": 0.45,
    }
    modified = {**safe, "ron_pullup_cload_proxy": 0.8, "clk_slew_proxy": 1.0}

    # 8 pairs enabled
    config_8 = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
        {"left": "ron_pulldown_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
        {"left": "cboot_cload_ratio", "right": "vgh_vth_margin", "weight": 0.25, "enabled": True},
        {"left": "ron_pullup_cload_proxy", "right": "vgh_vth_margin", "weight": 0.15, "enabled": True},
        {"left": "ron_pulldown_cload_proxy", "right": "vgl_off_margin", "weight": 0.15, "enabled": True},
        {"left": "cboot_cload_ratio", "right": "holding_droop_proxy", "weight": 0.15, "enabled": True},
        {"left": "pullup_pulldown_ratio", "right": "clk_slew_proxy", "weight": 0.10, "enabled": True},
        {"left": "vgh_vth_margin", "right": "vgl_off_margin", "weight": 0.10, "enabled": True},
    ]}
    result_8 = compute_capm_distance(modified, safe, config=config_8)

    # 3 pairs enabled (original)
    config_3 = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
        {"left": "ron_pulldown_cload_proxy", "right": "clk_slew_proxy", "weight": 0.25, "enabled": True},
        {"left": "cboot_cload_ratio", "right": "vgh_vth_margin", "weight": 0.25, "enabled": True},
    ]}
    result_3 = compute_capm_distance(modified, safe, config=config_3)

    assert result_8["tensor_distance"] >= result_3["tensor_distance"]


def test_coupling_per_pair_weight() -> None:
    a = {"ron_pullup_cload_proxy": 0.4, "clk_slew_proxy": 0.5, "vgh_vth_margin": 2.5}
    b = {"ron_pullup_cload_proxy": 0.8, "clk_slew_proxy": 1.0, "vgh_vth_margin": 2.0}

    config_low = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 0.01, "enabled": True},
    ]}
    config_high = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 1.0, "enabled": True},
    ]}

    result_low = compute_capm_distance(a, b, config=config_low)
    result_high = compute_capm_distance(a, b, config=config_high)

    assert result_high["tensor_distance"] > result_low["tensor_distance"]


def test_coupling_disabled_via_config() -> None:
    a = {"ron_pullup_cload_proxy": 0.4, "clk_slew_proxy": 0.5}
    b = {"ron_pullup_cload_proxy": 0.8, "clk_slew_proxy": 1.0}

    config_enabled = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 1.0, "enabled": True},
    ]}
    config_disabled = {"couplings": [
        {"left": "ron_pullup_cload_proxy", "right": "clk_slew_proxy", "weight": 1.0, "enabled": False},
    ]}

    result_enabled = compute_capm_distance(a, b, config=config_enabled)
    result_disabled = compute_capm_distance(a, b, config=config_disabled)

    assert result_enabled["tensor_distance"] > result_disabled["tensor_distance"]


def test_legacy_coupling_weight_backward_compatible() -> None:
    a = {"ron_pullup_cload_proxy": 0.4, "clk_slew_proxy": 0.5}
    b = {"ron_pullup_cload_proxy": 0.8, "clk_slew_proxy": 1.0}

    result = compute_capm_distance(a, b, config={"coupling_weight": 0.5})
    assert result["status"] == "ok"
    assert result["distance"] is not None


def test_penalty_function_types() -> None:
    delta = 0.3
    threshold = 0.5

    lin = _linear_penalty(delta, threshold)
    quad = _quadratic_penalty(delta, threshold)
    exp_ = _exponential_penalty(delta, threshold, alpha=2.0)

    assert lin == 0.6
    assert quad == 0.36
    assert exp_ > quad
    assert exp_ > lin


def test_penalty_config_per_feature() -> None:
    phi = {"vgh_vth_margin": 0.05, "ron_pullup_cload_proxy": 3.0}

    # Default (exponential, alpha=2.0)
    score_default = constraint_barrier_score(phi)

    # Per-feature quadratic
    config_quad = {"penalty_config": {
        "vgh_vth_margin": {"type": "quadratic"},
        "ron_pullup_cload_proxy": {"type": "quadratic"},
    }}
    score_quad = constraint_barrier_score(phi, config_quad)

    # Exponential with higher alpha
    config_steep = {"penalty_config": {
        "vgh_vth_margin": {"type": "exponential", "alpha": 4.0},
        "ron_pullup_cload_proxy": {"type": "exponential", "alpha": 4.0},
    }}
    score_steep = constraint_barrier_score(phi, config_steep)

    assert score_default > score_quad
    assert score_steep > score_default


def test_penalty_no_violation_returns_zero() -> None:
    phi = {"vgh_vth_margin": 3.0, "ron_pullup_cload_proxy": 0.5}
    score = constraint_barrier_score(phi)
    assert score == 0.0
