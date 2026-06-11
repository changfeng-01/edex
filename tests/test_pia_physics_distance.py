from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.physics_distance import (
    compute_physics_distance,
    distance_to_l1_physics,
    normalize_distance,
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
