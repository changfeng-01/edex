from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.labeling import assign_level_labels, infer_record_status, summarize_label_distribution


def test_labeler_assigns_l1_to_top_feasible_and_blocks_hard_failures() -> None:
    frame = pd.DataFrame(
        [
            {"sample_id": "a", "overall_score": 95, "hard_constraint_passed": True, "sim_success": True},
            {"sample_id": "b", "overall_score": 85, "hard_constraint_passed": True, "sim_success": True},
            {"sample_id": "c", "overall_score": 50, "hard_constraint_passed": False, "sim_success": True},
            {"sample_id": "d", "overall_score": 99, "hard_constraint_passed": False, "sim_success": False},
        ]
    )

    labeled = assign_level_labels(frame)

    assert labeled.loc[labeled["sample_id"] == "a", "level_label"].item() == "L1"
    assert labeled.loc[labeled["sample_id"] == "b", "level_label"].item() in {"L2", "L3"}
    assert labeled.loc[labeled["sample_id"] == "c", "level_label"].item() not in {"L1", "L2"}
    assert labeled.loc[labeled["sample_id"] == "d", "level_label"].item() == "L4"
    assert summarize_label_distribution(labeled)["L1"] == 1


def test_infer_record_status_keeps_predicted_only_out_of_evaluated_status() -> None:
    assert infer_record_status({"status": "predicted_only"}) == "predicted_only"
    assert infer_record_status({"sim_success": False}) == "sim_failed"
    assert infer_record_status({"hard_constraint_passed": False, "sim_success": True}) == "evaluated_soft_fail"
