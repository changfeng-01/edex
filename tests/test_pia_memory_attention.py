from __future__ import annotations

import numpy as np

from goa_eval.pia_ca_llso.memory_attention import (
    aggregate_history_context,
    attention_to_l1_mass,
    compute_attention,
)


def test_attention_weights_sum_to_one_and_aggregate_l1_mass() -> None:
    weights, status = compute_attention(np.array([1.0, 0.0]), np.array([[1.0, 0.0], [0.0, 1.0]]))
    assert status == "ok"
    assert round(float(weights.sum()), 6) == 1.0
    assert attention_to_l1_mass(weights, ["L1", "L4"]) > 0.5
    assert aggregate_history_context(weights, [10.0, 0.0]) > 5


def test_attention_unavailable_is_diagnostic_not_crash() -> None:
    weights, status = compute_attention(np.array([]), np.array([]))
    assert weights.size == 0
    assert status == "diagnostic_unavailable"
