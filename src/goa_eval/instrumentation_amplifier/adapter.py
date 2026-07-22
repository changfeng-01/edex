from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile
from goa_eval.domain import CircuitParameterProfile, CircuitTaskHead, evaluate_task_head
from goa_eval.instrumentation_amplifier.model import InstrumentationAmplifierModel
from goa_eval.instrumentation_amplifier.sensitivity import estimate_central_log_sensitivity
from goa_eval.transfer import (
    BarrierResult,
    LocalElectricalState,
    PhysicalEffect,
    PhysicalEffectPacket,
    SensitivityArtifact,
    project_physical_effect,
)


CANONICAL_EFFECTS = (
    "critical_time_log_delta",
    "output_headroom_normalized_delta",
    "power_log_delta",
    "mismatch_sensitivity_log_delta",
    "task_gain_margin_delta",
)
OBSERVABLE_METRICS = (
    "differential_gain",
    "common_mode_gain",
    "cmrr_db",
    "bandwidth_hz",
    "output_headroom_v",
    "slew_utilization",
    "power_w",
    "input_common_mode_margin_v",
)


def scenario_key(scenario: Mapping[str, Any] | None) -> str:
    values = scenario or {}
    corner = str(values.get("corner", "TT")).strip().upper()
    temperature = _number_text(values.get("temperature_c", 25.0))
    supply = _number_text(values.get("supply_v", values.get("VCC", 5.0)))
    return f"{corner}|{temperature}|{supply}"


def load_observed_scenarios(path: str | Path, *, sample_id: str) -> dict[str, dict[str, Any]]:
    frame = pd.read_csv(path)
    required = {"sample_id", "corner", "temperature_c", "supply_v"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("scenario CSV missing columns: " + ", ".join(missing))
    selected = frame[frame["sample_id"].astype(str) == str(sample_id)]
    observed: dict[str, dict[str, Any]] = {}
    for row in selected.to_dict(orient="records"):
        key = scenario_key(row)
        if key in observed:
            raise ValueError(f"duplicate observed scenario for {sample_id}: {key}")
        observed[key] = row
    return observed


def aggregate_scenario_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    usable = [result for result in results if _finite(result.get("distance")) is not None]
    if not usable:
        return {
            "status": "not_evaluable",
            "distance": None,
            "barrier": None,
            "worst_scenario": None,
        }
    total_weight = sum(max(float(result.get("weight", 1.0)), 0.0) for result in usable)
    if total_weight <= 0.0:
        total_weight = float(len(usable))
        weights = [1.0 for _ in usable]
    else:
        weights = [max(float(result.get("weight", 1.0)), 0.0) for result in usable]
    mean = sum(weight * float(result["distance"]) for weight, result in zip(weights, usable)) / total_weight
    worst = max(usable, key=lambda result: float(result["distance"]))
    barriers = [
        float((result.get("barrier") or {}).get("value", 0.0)) for result in usable
    ]
    return {
        "status": "ok" if len(usable) == len(results) else "partial",
        "distance": 0.5 * mean + 0.5 * float(worst["distance"]),
        "barrier": max(barriers, default=0.0),
        "worst_scenario": worst.get("scenario_key"),
        "scenario_count": len(results),
        "usable_scenario_count": len(usable),
    }


class InstrumentationAmplifierPhysicsAdapter:
    profile_name = "instrumentation_amplifier_three_opamp_compensated_v1"
    physics_version = "instrumentation_amplifier_three_opamp_v1"
    task_head_version = "instrumentation_amplifier_task_v1"

    def extract_local_state(
        self, row: Mapping[str, Any], scenario: Mapping[str, Any], profile: Mapping[str, Any]
    ) -> LocalElectricalState:
        design = {name: row[name] for name in ("R", "RG", "RD", "KD_plus", "KD_minus", "CF")}
        opamp = {
            name: row[name]
            for name in (
                "A0",
                "GBW",
                "SR",
                "Rout",
                "input_common_min_v",
                "input_common_max_v",
                "output_low_v",
                "output_high_v",
                "supply_current_a",
            )
            if row.get(name) is not None
        }
        environment = {**scenario, **{name: row[name] for name in ("Vd", "V_CM", "f", "VCC", "VEE", "RL", "power_w") if row.get(name) is not None}}
        evaluated = InstrumentationAmplifierModel(
            design, opamp_model=opamp, environment=environment
        ).evaluate()
        values = {name: _finite(evaluated.get(name)) for name in OBSERVABLE_METRICS}
        status = {
            name: evaluated.get("power_status", evaluated.get("model_status", "proxy"))
            if name == "power_w"
            else evaluated.get("model_status", "proxy")
            for name in OBSERVABLE_METRICS
        }
        return LocalElectricalState(
            scenario_key=scenario_key(scenario),
            values_si=values,
            feature_status=status,
            model_status=str(evaluated.get("model_status", "proxy")),
            diagnostics=evaluated,
        )

    def evaluate_barrier(self, state: LocalElectricalState, task_head: Any) -> BarrierResult:
        evaluation = evaluate_task_head(state.values_si, task_head)
        violations = tuple(
            name
            for name, result in evaluation.metric_results.items()
            if result.violation > 0.0
        )
        value = max(
            (result.violation for result in evaluation.metric_results.values()), default=0.0
        )
        if evaluation.status == "missing_required_metrics":
            status = "missing"
            value = max(value, 1.0)
        else:
            status = "violated" if violations else "ok"
        return BarrierResult(value, status, violations, state.scenario_key)

    def to_canonical_effects(
        self, state: LocalElectricalState, baseline: LocalElectricalState
    ) -> PhysicalEffectPacket:
        effects = {
            "critical_time_log_delta": _log_improvement(
                baseline.values_si.get("bandwidth_hz"), state.values_si.get("bandwidth_hz"), sign=1.0
            ),
            "output_headroom_normalized_delta": _linear_effect(
                baseline.values_si.get("output_headroom_v"), state.values_si.get("output_headroom_v"), 1.5
            ),
            "power_log_delta": _log_improvement(
                baseline.values_si.get("power_w"), state.values_si.get("power_w"), sign=-1.0
            ),
            "mismatch_sensitivity_log_delta": _log_improvement(
                baseline.values_si.get("common_mode_gain"), state.values_si.get("common_mode_gain"), sign=-1.0
            ),
            "task_gain_margin_delta": _linear_effect(
                baseline.values_si.get("gain_error_fraction"), state.values_si.get("gain_error_fraction"), -0.01
            ),
            "bootstrap_coupling_delta": PhysicalEffect("not_applicable"),
            "tft_region_margin_delta": PhysicalEffect("not_applicable"),
        }
        status = "proxy" if state.model_status == "proxy" else "supported"
        effects = {
            name: PhysicalEffect(status, effect.value, effect.uncertainty)
            if effect.status == "supported" and status == "proxy"
            else effect
            for name, effect in effects.items()
        }
        return PhysicalEffectPacket(
            source_agent="InstrumentationAmplifierAgent",
            source_profile=self.profile_name,
            model_version=self.physics_version,
            scenario_key=state.scenario_key,
            effects=effects,
            raw_si=state.values_si,
            applicability={"circuit_family": "instrumentation_amplifier"},
            evidence={
                "data_source": "analytic_model_proxy" if state.model_status == "proxy" else "explicit_opamp_model",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            },
        )

    def estimate_sensitivity(
        self, calibration: Any, operating_point: Mapping[str, Any]
    ) -> SensitivityArtifact:
        del calibration
        baseline = self.evaluate_scenario(
            operating_point,
            {},
            objectives={"target_differential_gain": operating_point.get("target_differential_gain", 1.0)},
            opamp_model={name: operating_point[name] for name in ("A0", "GBW", "SR", "Rout") if name in operating_point},
        )
        baseline_state = self._state_from_result(baseline)

        def response(design: dict[str, float]) -> Mapping[str, Any]:
            evaluated = self.evaluate_scenario(
                design,
                {},
                objectives={"target_differential_gain": operating_point.get("target_differential_gain", 1.0)},
            )
            packet = self.to_canonical_effects(self._state_from_result(evaluated), baseline_state)
            return {
                name: effect.value
                for name, effect in packet.effects.items()
                if effect.value is not None
            }

        design = {
            name: operating_point[name]
            for name in ("R", "RG", "RD", "KD_plus", "KD_minus", "CF")
            if name in operating_point
        }
        return estimate_central_log_sensitivity(
            response,
            design,
            effect_names=CANONICAL_EFFECTS,
            profile=self.profile_name,
            scenario_key="TT|25|5",
        )

    def project_effect(self, packet, sensitivity, parameter_profile):
        target = {
            name: effect.value
            for name, effect in packet.effects.items()
            if effect.status in {"supported", "proxy"} and effect.value is not None
        }
        jacobian = next(iter(sensitivity.scenario_jacobians.values()), {})
        return project_physical_effect(target, jacobian, parameter_profile, {})

    def evaluate_scenario(
        self,
        design: Mapping[str, Any],
        scenario: Mapping[str, Any],
        *,
        objectives: Mapping[str, Any],
        opamp_model: Mapping[str, Any] | None = None,
        observation: Mapping[str, Any] | None = None,
        pvt_coefficients: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = scenario_key(scenario)
        target = _finite(objectives.get("target_differential_gain"))
        if target is None or target <= 0.0:
            return {
                "scenario_key": key,
                "status": "not_evaluable",
                "pvt_status": "missing",
                "missing_required_inputs": ["target_differential_gain"],
                "metrics": {},
                "metric_status": {},
                "data_source": "analytic_model_proxy",
            }
        nominal = _is_nominal(scenario)
        observed = {
            name: parsed
            for name in OBSERVABLE_METRICS
            if (parsed := _finite((observation or {}).get(name))) is not None
        }
        if not nominal and not pvt_coefficients:
            metrics = dict(observed)
            metric_status = {
                name: "observed" if name in observed else "missing"
                for name in OBSERVABLE_METRICS
            }
            pvt_status = "partial_observed" if observed else "missing"
            if not observed:
                return {
                    "scenario_key": key,
                    "status": "not_evaluable",
                    "pvt_status": pvt_status,
                    "missing_required_inputs": ["pvt_coefficients_or_observation"],
                    "metrics": {},
                    "metric_status": {},
                    "data_source": "analytic_model_proxy",
                }
        else:
            adjusted_model = dict(opamp_model or {})
            if not nominal:
                try:
                    adjusted_model = _apply_pvt(
                        adjusted_model, scenario, pvt_coefficients or {}
                    )
                except ValueError as exc:
                    return {
                        "scenario_key": key,
                        "status": "not_evaluable",
                        "pvt_status": "missing",
                        "missing_required_inputs": [str(exc)],
                        "metrics": dict(observed),
                        "metric_status": {
                            name: "observed" for name in observed
                        },
                        "data_source": (
                            "real_simulation_csv"
                            if observed
                            else "analytic_model_proxy"
                        ),
                        "engineering_validity": "simulation_only",
                        "must_resimulate": True,
                    }
            environment = {
                "Vd": scenario.get("Vd", 0.1),
                "V_CM": scenario.get("V_CM", 0.0),
                "f": scenario.get("f", 1.0e3),
                "VCC": scenario.get("VCC", scenario.get("supply_v", 5.0)),
                "VEE": scenario.get("VEE", -float(scenario.get("supply_v", 5.0))),
                "RL": scenario.get("RL", 10.0e3),
            }
            evaluated = InstrumentationAmplifierModel(
                design, opamp_model=adjusted_model, environment=environment
            ).evaluate()
            metrics = {
                name: value
                for name in OBSERVABLE_METRICS
                if (value := _finite(evaluated.get(name), allow_positive_infinity=True)) is not None
            }
            metric_status = {
                name: (
                    evaluated.get("power_status", "missing")
                    if name == "power_w"
                    else evaluated.get("model_status", "proxy")
                )
                for name in metrics
            }
            pvt_status = "nominal_model" if nominal else "proxy"
            metrics.update(observed)
            metric_status.update({name: "observed" for name in observed})
        metrics["gain_error_fraction"] = abs(float(metrics.get("differential_gain", float("nan"))) - target) / target
        metric_status["gain_error_fraction"] = metric_status.get("differential_gain", "missing")
        task = _task_head()
        task_evaluation = evaluate_task_head(metrics, task)
        state = LocalElectricalState(key, metrics, metric_status, pvt_status)
        barrier = self.evaluate_barrier(state, task)
        data_source = "real_simulation_csv" if observed else "analytic_model_proxy"
        return {
            "scenario_key": key,
            "status": "not_evaluable" if task_evaluation.score is None else task_evaluation.status,
            "pvt_status": pvt_status,
            "missing_required_inputs": [],
            "metrics": metrics,
            "metric_status": metric_status,
            "task_evaluation": task_evaluation.as_dict(),
            "barrier": barrier.as_dict(),
            "distance": None if task_evaluation.score is None else 1.0 - task_evaluation.score,
            "weight": float(scenario.get("weight", 1.0)),
            "data_source": data_source,
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        }

    @staticmethod
    def _state_from_result(result: Mapping[str, Any]) -> LocalElectricalState:
        return LocalElectricalState(
            str(result.get("scenario_key", "TT|25|5")),
            dict(result.get("metrics", {})),
            dict(result.get("metric_status", {})),
            str(result.get("pvt_status", "proxy")),
        )


def instrumentation_parameter_profile() -> CircuitParameterProfile:
    profile = resolve_circuit_profile(
        InstrumentationAmplifierPhysicsAdapter.profile_name, load_circuit_profiles()
    )
    return CircuitParameterProfile.from_circuit_profile(profile)


def _task_head() -> CircuitTaskHead:
    return CircuitTaskHead.from_mapping(
        {
            "name": "instrumentation_amplifier_task_v1",
            "metrics": {
                "gain_error": {"feature": "gain_error_fraction", "direction": "smaller_better", "maximum": 0.01, "scale": 0.01, "weight": 0.25},
                "cmrr": {"feature": "cmrr_db", "direction": "larger_better", "minimum": 60.0, "scale": 20.0, "weight": 0.25},
                "bandwidth": {"feature": "bandwidth_hz", "direction": "larger_better", "minimum": 10.0e3, "scale": 10.0e3, "weight": 0.15},
                "headroom": {"feature": "output_headroom_v", "direction": "larger_better", "minimum": 1.5, "scale": 1.5, "weight": 0.15},
                "slew": {"feature": "slew_utilization", "direction": "smaller_better", "maximum": 1.0, "scale": 1.0, "weight": 0.10},
                "power": {"feature": "power_w", "direction": "smaller_better", "scale": 0.01, "weight": 0.10, "required": False},
            },
        }
    )


def _apply_pvt(
    model: Mapping[str, Any], scenario: Mapping[str, Any], coefficients: Mapping[str, Any]
) -> dict[str, Any]:
    adjusted = dict(model)
    corner = str(scenario.get("corner", "TT")).upper()
    corner_values = dict((coefficients.get("corners", {}) or {}).get(corner, {}))
    temperature_values = dict(coefficients.get("temperature", {}) or {})
    supply_values = dict(coefficients.get("supply", {}) or {})
    if corner != "TT" and not corner_values:
        raise ValueError(f"missing PVT corner coefficients for {corner}")
    temperature = float(scenario.get("temperature_c", 25.0))
    reference_temperature = float(temperature_values.get("reference_c", 25.0))
    delta_temperature = temperature - reference_temperature
    if not math.isclose(delta_temperature, 0.0) and not any(
        str(name).endswith("_per_c") for name in temperature_values
    ):
        raise ValueError("missing PVT temperature coefficients")
    supply = float(scenario.get("supply_v", supply_values.get("reference_v", 5.0)))
    reference_supply = float(supply_values.get("reference_v", 5.0))
    if not math.isclose(supply, reference_supply) and not any(
        str(name).endswith("_exponent") for name in supply_values
    ):
        raise ValueError("missing PVT supply coefficients")
    for name, raw in list(adjusted.items()):
        parsed = _finite(raw)
        if parsed is None:
            continue
        value = parsed * float(corner_values.get(name, 1.0))
        if f"{name}_per_c" in temperature_values:
            value *= 1.0 + float(temperature_values[f"{name}_per_c"]) * delta_temperature
        if f"{name}_exponent" in supply_values:
            value *= (supply / reference_supply) ** float(supply_values[f"{name}_exponent"])
        if name in {"A0", "GBW", "SR", "Rout", "supply_current_a"} and value <= 0.0:
            raise ValueError(f"PVT coefficients make {name} non-positive")
        adjusted[name] = value
    return adjusted


def _log_improvement(baseline: Any, value: Any, *, sign: float) -> PhysicalEffect:
    base = _finite(baseline)
    current = _finite(value)
    if base is None or current is None or base <= 0.0 or current <= 0.0:
        return PhysicalEffect("missing")
    return PhysicalEffect("supported", sign * math.log(current / base), 0.25)


def _linear_effect(baseline: Any, value: Any, scale: float) -> PhysicalEffect:
    base = _finite(baseline)
    current = _finite(value)
    if base is None or current is None or scale == 0.0:
        return PhysicalEffect("missing")
    return PhysicalEffect("supported", (current - base) / scale, 0.25)


def _is_nominal(scenario: Mapping[str, Any]) -> bool:
    return (
        str(scenario.get("corner", "TT")).upper() == "TT"
        and math.isclose(float(scenario.get("temperature_c", 25.0)), 25.0)
        and math.isclose(float(scenario.get("supply_v", 5.0)), 5.0)
    )


def _number_text(value: Any) -> str:
    return f"{float(value):g}"


def _finite(value: Any, *, allow_positive_infinity: bool = False) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(parsed) or (allow_positive_infinity and parsed == float("inf")):
        return parsed
    return None
