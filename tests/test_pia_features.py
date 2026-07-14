from __future__ import annotations

import json

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


def test_goa_v2_features_use_optional_physical_inputs_and_report_fallbacks() -> None:
    base = {
        "TFT_pullup_W": 40.0,
        "TFT_pullup_L": 4.0,
        "TFT_pulldown_W": 20.0,
        "TFT_pulldown_L": 4.0,
        "C_boot": 4.0,
        "C_load": 2.0,
        "CLK_amp": 5.0,
        "CLK_rise_time": 0.2,
        "CLK_fall_time": 0.3,
        "VGH": 5.0,
        "VGL": -3.0,
        "Vth_shift": 1.0,
    }
    frame = pd.DataFrame(
        [
            {
                **base,
                "mu_pullup_cm2_v_s": 2.0,
                "mu_pulldown_cm2_v_s": 1.5,
                "cox_f_per_cm2": 1.0,
                "C_parasitic": 0.5,
            },
            base,
        ]
    )

    features, report = extract_physics_features(frame, {"profile": "goa", "electrical_features_enabled": True})
    full_status = json.loads(features.loc[0, "physics_feature_status_json"])
    fallback_status = json.loads(features.loc[1, "physics_feature_status_json"])

    assert features.loc[0, "effective_load_capacitance"] == 2.5
    assert features.loc[0, "pullup_rc_delay_proxy_v2"] < features.loc[1, "pullup_rc_delay_proxy_v2"]
    assert features.loc[0, "bootstrap_coupling_factor"] == 4.0 / 6.5
    assert features.loc[0, "bootstrap_voltage_proxy"] == 5.0 * 4.0 / 6.5
    assert full_status["pullup_rc_delay_proxy_v2"] == "physical"
    assert fallback_status["pullup_rc_delay_proxy_v2"] == "proxy_fallback"
    assert report["electrical_features_enabled"] is True
