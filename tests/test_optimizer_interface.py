import pytest

from goa_eval.optimizer import (
    OptimizationRequest,
    OptimizationResult,
    CircuitPilotOptimizer,
    load_param_space,
    propose_candidates,
    rank_candidates,
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
