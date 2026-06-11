from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.raw_distance import distance_to_l1_raw, normalize_raw_parameters, select_by_raw_distance


def test_raw_distance_baseline_selects_candidates() -> None:
    history = pd.DataFrame(
        [
            {"sample_id": "h1", "x": 0.0, "y": 0.0, "level_label": "L1"},
            {"sample_id": "h2", "x": 1.0, "y": 1.0, "level_label": "L2"},
        ]
    )
    candidates = pd.DataFrame([{"candidate_id": "c1", "x": 0.1, "y": 0.1}, {"candidate_id": "c2", "x": 0.9, "y": 0.9}])

    assert list(normalize_raw_parameters(candidates, ["x", "y"]).columns) == ["x", "y"]
    assert distance_to_l1_raw(candidates.iloc[0], history, ["x", "y"])["distance"] < 0.3
    assert len(select_by_raw_distance(candidates, history, top_k=1, parameter_names=["x", "y"])) == 1
