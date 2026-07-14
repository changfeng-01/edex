from __future__ import annotations

import pandas as pd
import pytest

from goa_eval.pia_ca_llso.physics_distance import (
    _exponential_penalty,
    _linear_penalty,
    _quadratic_penalty,
    build_capm_distance_context,
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


def _v2_history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_id": f"h{index}",
                "level_label": "L1" if index >= 3 else "L2",
                "overall_score": 70.0 + index * 5.0,
                "hard_constraint_passed": True,
                "cboot_cload_ratio": 0.8 + index * 0.1,
                "pullup_pulldown_ratio": 0.9 + index * 0.05,
                "ron_pullup_cload_proxy": 0.8 - index * 0.05,
                "ron_pulldown_cload_proxy": 0.9 - index * 0.05,
                "vgh_vth_margin": 1.5 + index * 0.2,
                "vgl_off_margin": 1.2 + index * 0.2,
                "clk_slew_proxy": 0.8 - index * 0.05,
            }
            for index in range(5)
        ]
    )


def test_v2_similarity_is_zero_for_same_point_even_when_barrier_is_positive() -> None:
    history = _v2_history()
    context = build_capm_distance_context(history, config={"metric_version": "v2"})
    risky = history.iloc[0].to_dict()
    risky["vgh_vth_margin"] = 0.05

    result = compute_capm_distance(risky, risky, config={"metric_version": "v2"}, context=context)

    assert result["similarity_distance"] == 0.0
    assert result["barrier_cost"] > 0.0
    assert result["distance"] > 0.0
    assert result["metric_version"] == "v2"


def test_v2_history_normalization_is_invariant_to_consistent_unit_scaling() -> None:
    history = _v2_history()
    candidate = history.iloc[1].to_dict()
    reference = history.iloc[4].to_dict()
    scaled_history = history.copy()
    scaled_candidate = dict(candidate)
    scaled_reference = dict(reference)
    for column in ["vgh_vth_margin", "vgl_off_margin", "clk_slew_proxy"]:
        scaled_history[column] *= 1000.0
        scaled_candidate[column] *= 1000.0
        scaled_reference[column] *= 1000.0

    context = build_capm_distance_context(history, config={"metric_version": "v2"})
    scaled_context = build_capm_distance_context(scaled_history, config={"metric_version": "v2"})
    original = compute_capm_distance(candidate, reference, config={"metric_version": "v2"}, context=context)
    scaled = compute_capm_distance(
        scaled_candidate,
        scaled_reference,
        config={"metric_version": "v2"},
        context=scaled_context,
    )

    assert scaled["similarity_distance"] == pytest.approx(original["similarity_distance"])


def test_v2_weighted_missing_and_proxy_fallback_penalties_are_reported() -> None:
    history = _v2_history()
    weights = {"vgh_vth_margin": 4.0, "clk_slew_proxy": 1.0}
    context = build_capm_distance_context(history, weights=weights, config={"metric_version": "v2"})
    complete = history.iloc[3].to_dict()
    incomplete = dict(complete)
    incomplete["vgh_vth_margin"] = None
    incomplete["physics_feature_status_json"] = '{"clk_slew_proxy":"proxy_fallback"}'

    result = compute_capm_distance(incomplete, complete, weights, {"metric_version": "v2"}, context)

    assert result["missing_penalty"] == pytest.approx(0.8)
    assert result["proxy_fallback_penalty"] == pytest.approx(0.2)


def test_legacy_metric_preserves_previous_pair_formula() -> None:
    safe = {
        "cboot_cload_ratio": 1.2,
        "pullup_pulldown_ratio": 1.0,
        "ron_pullup_cload_proxy": 0.4,
        "ron_pulldown_cload_proxy": 0.4,
        "vgh_vth_margin": 2.5,
        "vgl_off_margin": 2.0,
        "clk_slew_proxy": 0.5,
    }
    modified = {**safe, "clk_slew_proxy": 0.7}

    result = compute_capm_distance(
        modified,
        safe,
        config={"metric_version": "legacy", "coupling_enabled": False},
    )

    assert result["tensor_distance"] == pytest.approx((1.2 * 0.2**2) ** 0.5)
    assert result["metric_version"] == "legacy"


def test_v2_geodesic_is_independent_of_unrelated_candidate_pool_members() -> None:
    history = _v2_history()
    candidate = pd.DataFrame([{"candidate_id": "target", **history.iloc[2].to_dict()}])
    unrelated = pd.DataFrame(
        [
            {"candidate_id": "unrelated", **history.iloc[0].to_dict(), "vgh_vth_margin": 20.0},
            *candidate.to_dict("records"),
        ]
    )

    single = physics_geodesic_distance_to_l1(candidate, history, config={"metric_version": "v2"})
    pooled = physics_geodesic_distance_to_l1(unrelated, history, config={"metric_version": "v2"})

    pooled_target = pooled.loc[pooled["candidate_id"] == "target"].iloc[0]
    assert pooled_target["capm_geodesic_distance_to_l1"] == pytest.approx(
        single.loc[0, "capm_geodesic_distance_to_l1"]
    )
    assert pooled_target["capm_l1_aggregation_status"].startswith("softmin")
