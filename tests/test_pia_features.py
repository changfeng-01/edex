from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.features import extract_physics_features, validate_no_leakage


def test_physics_features_handle_missing_inputs_and_prevent_metric_leakage() -> None:
    frame = pd.DataFrame(
        [{"TFT_pullup_W": 400, "TFT_pullup_L": 5, "TFT_pulldown_W": 200, "TFT_pulldown_L": 5, "overall_score": 99}]
    )

    features, report = extract_physics_features(frame, {"profile": "goa"})

    assert features.loc[0, "pullup_w_l"] == 80
    assert features.loc[0, "pullup_pulldown_ratio"] == 2
    assert "C_boot" in report["missing_inputs"]
    assert validate_no_leakage(features.columns, ["overall_score", "delay"]) == []
    assert "overall_score" in validate_no_leakage(["pullup_w_l", "overall_score"], ["overall_score"])
