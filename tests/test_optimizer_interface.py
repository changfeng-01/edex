import pytest
import pandas as pd

from goa_eval.optimizer import (
    OptimizationRequest,
    OptimizationResult,
    CircuitPilotOptimizer,
    constrained_random_candidates,
    load_param_space,
    propose_candidates,
    rank_candidates,
    write_candidate_outputs,
)


def test_optimizer_interface_is_explicit_placeholder():
    request = OptimizationRequest(parameter_space={"vdd": [10.0, 15.0]}, objective="overall_score")
    optimizer = CircuitPilotOptimizer()

    with pytest.raises(NotImplementedError, match="not implemented"):
        optimizer.optimize(request)

    result = OptimizationResult(status="not_implemented", best_parameters=None, message="placeholder")
    assert result.status == "not_implemented"
    assert result.best_parameters is None


def test_optimizer_rule_helpers_propose_and_rank_candidates(tmp_path):
    param_space = tmp_path / "param_space.yaml"
    param_space.write_text(
        """
parameters:
  C_store: [1pF, 2pF]
  R_driver: [10k, 8k]
  W_nmos: [1u, 1.5u]
""".strip(),
        encoding="utf-8",
    )
    loaded = load_param_space(param_space)
    recommendations = [
        {
            "recommendation_id": "ripple_hold_window_review",
            "trigger_metric": "Max_ripple",
            "next_tuning_actions": "增大保持电容或检查泄漏路径。",
        },
        {
            "recommendation_id": "delay_drive_load_review",
            "trigger_metric": "Delay_mean",
            "next_tuning_actions": "调整驱动能力。",
        },
    ]

    candidates = propose_candidates(loaded, recommendations)
    ranked = rank_candidates(candidates)

    assert any(candidate["parameter"] == "C_store" for candidate in candidates)
    assert any(candidate["parameter"] == "R_driver" for candidate in candidates)
    assert ranked[0]["priority"] >= ranked[-1]["priority"]


def test_propose_candidates_expands_simple_parameter_values():
    param_space = {
        "C_store": ["1pF", "2pF"],
        "R_driver": ["10k"],
    }
    recommendations = [
        {
            "recommendation_id": "ripple_hold_window_review",
            "trigger_metric": "Max_ripple",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        }
    ]

    candidates = rank_candidates(propose_candidates(param_space, recommendations))

    assert [candidate["candidate_value"] for candidate in candidates if candidate["parameter"] == "C_store"] == ["1pF", "2pF"]
    assert all(candidate["data_source"] == "real_simulation_csv" for candidate in candidates)
    assert all(candidate["engineering_validity"] == "simulation_only" for candidate in candidates)


def test_propose_candidates_supports_unit_values_parameter_space(tmp_path):
    param_space = tmp_path / "param_space.yaml"
    param_space.write_text(
        """
parameters:
  capacitance:
    unit: F
    values: [8.0e-13, 1.0e-12]
  drive_resistance:
    unit: ohm
    values: [1000, 1500]
  transistor_width:
    unit: m
    values: [8.0e-7]
""".strip(),
        encoding="utf-8",
    )
    recommendations = [
        {"recommendation_id": "ripple_hold_window_review", "trigger_metric": "Max_ripple"},
        {"recommendation_id": "delay_drive_load_review", "trigger_metric": "Delay_mean"},
    ]

    candidates = rank_candidates(propose_candidates(load_param_space(param_space), recommendations))

    assert any(candidate["parameter"] == "capacitance" and candidate["candidate_unit"] == "F" for candidate in candidates)
    assert any(candidate["parameter"] == "drive_resistance" and candidate["candidate_unit"] == "ohm" for candidate in candidates)
    assert any(candidate["parameter"] == "transistor_width" and candidate["candidate_unit"] == "m" for candidate in candidates)


def test_propose_candidates_returns_empty_for_info_only_recommendation():
    recommendations = [{"recommendation_id": "no_rule_failure_detected", "trigger_metric": "none"}]

    assert propose_candidates({"C_store": ["1pF"]}, recommendations) == []


def test_write_candidate_outputs_writes_fixed_csv_and_boundary_markdown(tmp_path):
    candidates = [
        {
            "candidate_id": "cand_001",
            "priority": 90,
            "parameter": "C_store",
            "direction": "increase",
            "candidate_value": "2pF",
            "candidate_unit": "",
            "source_recommendation": "ripple_hold_window_review",
            "trigger_metric": "Max_ripple",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        }
    ]
    csv_path = tmp_path / "next_candidates.csv"
    md_path = tmp_path / "next_candidates.md"

    write_candidate_outputs(candidates, csv_path=csv_path, markdown_path=md_path)

    table = pd.read_csv(csv_path)
    assert list(table.columns[:12]) == [
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
    ]
    assert {"strategy", "candidate_kind", "changed_parameters", "parameters_json", "search_score", "rationale"} <= set(table.columns)
    content = md_path.read_text(encoding="utf-8")
    assert "simulation_only" in content
    assert "不是实物测试结果" in content
    assert "自动优化闭环" in content


def test_constrained_random_candidates_are_reproducible_and_limited():
    recommendations = [
        {"recommendation_id": "ripple_hold_window_review", "trigger_metric": "Max_ripple"},
        {"recommendation_id": "delay_drive_load_review", "trigger_metric": "Delay_mean"},
    ]
    param_space = {
        "capacitance": {"unit": "F", "values": [8.0e-13, 1.0e-12, 1.2e-12]},
        "drive_resistance": {"unit": "ohm", "values": [1000, 1500, 2000]},
        "transistor_width": {"unit": "m", "values": [8.0e-7, 1.0e-6]},
    }

    first = constrained_random_candidates(param_space, recommendations, max_candidates=4, seed=7)
    second = constrained_random_candidates(param_space, recommendations, max_candidates=4, seed=7)

    assert first == second
    assert len(first) == 4
    assert any(candidate["candidate_kind"] == "single_parameter" for candidate in first)
    assert any(candidate["candidate_kind"] == "two_parameter_combo" for candidate in first)
    assert all(candidate["strategy"] == "constrained_random" for candidate in first)
    assert all("parameters_json" in candidate for candidate in first)


def test_constrained_random_candidates_respect_baseline_direction():
    recommendations = [
        {"recommendation_id": "ripple_hold_window_review", "trigger_metric": "Max_ripple"},
        {"recommendation_id": "delay_drive_load_review", "trigger_metric": "Delay_mean"},
    ]
    param_space = {
        "capacitance": {"unit": "F", "values": [8.0e-13, 1.0e-12, 1.2e-12]},
        "drive_resistance": {"unit": "ohm", "values": [1000, 1500, 2000]},
    }

    candidates = constrained_random_candidates(
        param_space,
        recommendations,
        max_candidates=10,
        seed=42,
        baseline_params={"capacitance": 1.0e-12, "drive_resistance": 1500},
    )

    for candidate in candidates:
        params = candidate["parameters_json"]
        if "capacitance" in params:
            assert float(params["capacitance"]) > 1.0e-12
        if "drive_resistance" in params:
            assert float(params["drive_resistance"]) < 1500


def test_constrained_random_candidates_prioritize_severe_constraint_penalties():
    recommendations = [
        {
            "recommendation_id": "ripple_hold_window_review",
            "trigger_metric": "Max_ripple",
            "metric_penalty_severity": "fail",
            "metric_penalty_deduction": 15.0,
        },
        {
            "recommendation_id": "overlap_timing_review",
            "trigger_metric": "Max_overlap_ratio",
            "metric_penalty_severity": "critical",
            "metric_penalty_deduction": 90.0,
        },
    ]
    param_space = {
        "capacitance": {"unit": "F", "values": [1.2e-12]},
        "drive_resistance": {"unit": "ohm", "values": [2000]},
    }

    candidates = constrained_random_candidates(param_space, recommendations, max_candidates=2, seed=1)

    assert candidates[0]["trigger_metric"] == "Max_overlap_ratio"
    assert float(candidates[0]["search_score"]) > float(candidates[1]["search_score"])
    assert "critical" in candidates[0]["rationale"]


def test_constrained_random_candidates_return_empty_for_info_only_recommendation():
    recommendations = [{"recommendation_id": "no_rule_failure_detected", "trigger_metric": "none"}]

    assert constrained_random_candidates({"capacitance": {"unit": "F", "values": [1.0e-12]}}, recommendations) == []
