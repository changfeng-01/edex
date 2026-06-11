from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.selector import select_candidates


def test_selector_returns_top_k_with_candidate_roles() -> None:
    history = pd.DataFrame(
        [{"sample_id": "h1", "pullup_w_l": 80.0, "level_label": "L1", "overall_score": 92, "hard_constraint_passed": True}]
    )
    candidates = pd.DataFrame(
        [
            {"candidate_id": f"c{i}", "pullup_w_l": 80.0 + i, "p_l1": 0.9 - i * 0.1, "p_hard_pass": 0.8, "predicted_score": 80 - i}
            for i in range(6)
        ]
    )

    result = select_candidates(candidates, history, strategy="pia_physics_distance", top_k=4)

    assert len(result.selected_candidates) == 4
    assert set(result.selected_candidates["candidate_role"]).issuperset({"exploitation_best", "l1_center"})
