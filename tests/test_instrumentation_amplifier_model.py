from __future__ import annotations

import math

import pytest

from goa_eval.instrumentation_amplifier import (
    InstrumentationAmplifierModel,
    derive_components,
    parse_electrical_value,
)


BASE_DESIGN = {
    "R": 10.0e3,
    "RG": 2.0e3,
    "RD": 10.0e3,
    "KD_plus": 1.2,
    "KD_minus": 1.2,
    "CF": 10.0e-12,
}


def test_component_parameterization_preserves_compensation_time_constants() -> None:
    components = derive_components(BASE_DESIGN)

    assert components.R1 == components.R2 == pytest.approx(10.0e3)
    assert components.R3 == components.R4 == pytest.approx(10.0e3)
    assert components.R5 * components.C5 == pytest.approx(components.RD * components.CF)
    assert components.R6 * components.C6 == pytest.approx(components.RD * components.CF)


def test_variations_apply_to_derived_resistors_and_must_remain_above_minus_one() -> None:
    components = derive_components(BASE_DESIGN, {"delta1": 0.1, "delta6": -0.2})

    assert components.R1 == pytest.approx(11.0e3)
    assert components.R6 == pytest.approx(0.8 * 1.2 * 10.0e3)
    with pytest.raises(ValueError, match="greater than -1"):
        derive_components(BASE_DESIGN, {"delta3": -1.0})


def test_ideal_symmetric_dc_gain_matches_closed_form_and_rd_cancels() -> None:
    expected = (1.0 + 2.0 * BASE_DESIGN["R"] / BASE_DESIGN["RG"]) * 1.2
    first = InstrumentationAmplifierModel(BASE_DESIGN).transfer_metrics()
    changed_rd = InstrumentationAmplifierModel(
        {**BASE_DESIGN, "RD": 45.0e3}
    ).transfer_metrics()

    assert first.model_status == "proxy"
    assert first.differential_gain == pytest.approx(expected, rel=1.0e-10)
    assert changed_rd.differential_gain == pytest.approx(expected, rel=1.0e-10)
    assert first.common_mode_gain_status == "ideal_infinite"
    assert math.isinf(first.cmrr_db)


def test_input_polarity_exchange_changes_output_sign_but_not_gain_magnitude() -> None:
    model = InstrumentationAmplifierModel(BASE_DESIGN)

    forward = model.solve(0.0, 1.0, frequency_hz=0.0)
    reverse = model.solve(1.0, 0.0, frequency_hz=0.0)

    assert forward.output_v == pytest.approx(-reverse.output_v, rel=1.0e-10)


def test_kd_ratio_mismatch_monotonically_degrades_cmrr() -> None:
    small = InstrumentationAmplifierModel(
        {**BASE_DESIGN, "KD_minus": 1.19}
    ).transfer_metrics()
    large = InstrumentationAmplifierModel(
        {**BASE_DESIGN, "KD_minus": 1.0}
    ).transfer_metrics()

    assert small.common_mode_gain_status == "resolved"
    assert large.common_mode_gain_status == "resolved"
    assert small.cmrr_db > large.cmrr_db


def test_finite_gain_model_uses_all_three_opamps_and_finds_bandwidth() -> None:
    result = InstrumentationAmplifierModel(
        BASE_DESIGN,
        opamp_model={"A0": 1.0e5, "GBW": 1.0e6, "Rout": 50.0},
        environment={"RL": 10.0e3},
    ).transfer_metrics()

    assert result.model_status == "physical_model"
    assert 0.0 < result.differential_gain < (1.0 + 2.0 * 10.0e3 / 2.0e3) * 1.2
    assert result.bandwidth_status == "resolved"
    assert result.bandwidth_hz is not None and result.bandwidth_hz > 0.0
    assert result.matrix_condition_number > 0.0


def test_finite_output_resistance_makes_heavier_load_reduce_gain() -> None:
    model = {"A0": 1.0e5, "GBW": 1.0e6, "Rout": 200.0}
    light = InstrumentationAmplifierModel(
        BASE_DESIGN, opamp_model=model, environment={"RL": 100.0e3}
    ).transfer_metrics()
    heavy = InstrumentationAmplifierModel(
        BASE_DESIGN, opamp_model=model, environment={"RL": 1.0e3}
    ).transfer_metrics()

    assert heavy.differential_gain < light.differential_gain


def test_uncompensated_ideal_reference_reports_no_bandwidth_crossing() -> None:
    result = InstrumentationAmplifierModel(
        {**BASE_DESIGN, "CF": 0.0}, reference_uncompensated=True
    ).transfer_metrics()

    assert result.bandwidth_hz is None
    assert result.bandwidth_status == "no_crossing"


def test_slew_headroom_common_mode_and_power_have_explicit_evidence_status() -> None:
    model = InstrumentationAmplifierModel(
        BASE_DESIGN,
        opamp_model={
            "A0": 1.0e5,
            "GBW": 1.0e6,
            "SR": 0.5e6,
            "Rout": 50.0,
            "input_common_min_v": -1.0,
            "input_common_max_v": 1.0,
            "output_low_v": -4.0,
            "output_high_v": 4.0,
            "supply_current_a": 1.0e-3,
        },
        environment={
            "Vd": 0.1,
            "V_CM": 0.0,
            "f": 10.0e3,
            "VCC": 5.0,
            "VEE": -5.0,
            "RL": 10.0e3,
        },
    )

    result = model.evaluate()

    assert result["slew_utilization"] == pytest.approx(
        2.0 * math.pi * 10.0e3 * result["output_peak_v"] / 0.5e6
    )
    assert result["input_common_mode_status"] == "physical_model"
    assert result["output_headroom_v"] < 4.0
    assert result["power_w"] == pytest.approx(10.0e-3)
    assert result["power_status"] == "physical_model"

    proxy = InstrumentationAmplifierModel(BASE_DESIGN).evaluate()
    assert proxy["power_w"] is None
    assert proxy["power_status"] == "missing"
    assert proxy["slew_utilization"] is None


def test_reference_uncompensated_is_math_only_and_invalid_units_fail_closed() -> None:
    uncompensated = derive_components({**BASE_DESIGN, "CF": 0.0}, reference_uncompensated=True)

    assert uncompensated.C5 == uncompensated.C6 == 0.0
    with pytest.raises(ValueError, match="positive"):
        derive_components({**BASE_DESIGN, "CF": 0.0})
    assert parse_electrical_value(10.0, "kohm", quantity="resistance") == pytest.approx(10.0e3)
    assert parse_electrical_value(10.0, "pF", quantity="capacitance") == pytest.approx(10.0e-12)
    with pytest.raises(ValueError, match="unsupported unit"):
        parse_electrical_value(1.0, "banana", quantity="resistance")
