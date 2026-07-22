from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from goa_eval.domain import CircuitParameterProfile
from goa_eval.multi_agent.agents._utils import add_message
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.transfer.action_projection import project_physical_effect
from goa_eval.transfer.physics_protocol import PhysicalEffectPacket, SensitivityArtifact


def coordinate_transfer(
    source_packet: PhysicalEffectPacket | Mapping[str, Any],
    target_sensitivity: SensitivityArtifact | Mapping[str, Any],
    parameter_profile: CircuitParameterProfile | Mapping[str, Any],
    operating_point: Mapping[str, Any],
    *,
    regularization: float = 1.0e-3,
    minimum_alignment: float = 0.5,
    maximum_relative_residual: float = 0.5,
    max_log_step: float = 0.5,
    maximum_condition_number: float = 1.0e6,
    maximum_normalized_uncertainty: float = 0.5,
    maximum_iterations: int = 5,
) -> dict[str, Any]:
    packet = (
        source_packet
        if isinstance(source_packet, PhysicalEffectPacket)
        else PhysicalEffectPacket.from_mapping(source_packet)
    )
    sensitivity = (
        target_sensitivity
        if isinstance(target_sensitivity, SensitivityArtifact)
        else SensitivityArtifact.from_mapping(target_sensitivity)
    )
    profile = (
        parameter_profile
        if isinstance(parameter_profile, CircuitParameterProfile)
        else CircuitParameterProfile.from_mapping(parameter_profile)
    )
    scenario_jacobians = dict(sensitivity.scenario_jacobians)
    target_supported = {
        feature
        for jacobian in scenario_jacobians.values()
        for feature in jacobian
    }
    supported: list[str] = []
    rejected: dict[str, str] = {}
    target_effect: dict[str, float] = {}
    for name, effect in packet.effects.items():
        if effect.status not in {"supported", "proxy"}:
            rejected[name] = effect.status
        elif name not in target_supported:
            rejected[name] = "not_applicable_in_target"
        elif effect.value is None or not math.isfinite(float(effect.value)):
            rejected[name] = "missing"
        else:
            supported.append(name)
            target_effect[name] = float(effect.value)

    if not supported or not scenario_jacobians:
        return _rejected("unsupported_effect", supported, rejected)

    uncertainties = [
        float(sensitivity.normalized_uncertainty.get(feature, 0.0))
        for feature in supported
    ]
    normalized_uncertainty = max(uncertainties, default=0.0)
    ood_diagnostics = _assess_ood(packet, sensitivity, target_effect)
    transfer_confidence = _transfer_confidence(
        packet, sensitivity, normalized_uncertainty, ood_diagnostics
    )
    if ood_diagnostics["status"] == "out_of_distribution":
        result = _rejected("out_of_distribution", supported, rejected)
        result["ood_diagnostics"] = ood_diagnostics
        result["transfer_confidence"] = transfer_confidence
        return result
    projection, selected_parameters, dropped_parameters, iterations = _iterative_projection(
        target_effect=target_effect,
        scenario_jacobians=scenario_jacobians,
        features=supported,
        profile=profile,
        operating_point=operating_point,
        regularization=regularization,
        minimum_alignment=minimum_alignment,
        maximum_relative_residual=maximum_relative_residual,
        max_log_step=max_log_step,
        maximum_condition_number=maximum_condition_number,
        normalized_uncertainty=normalized_uncertainty,
        maximum_normalized_uncertainty=maximum_normalized_uncertainty,
        maximum_iterations=maximum_iterations,
    )
    suggestions = []
    if projection.accepted:
        for scale in (0.25, 0.5, 1.0):
            suggestions.append(
                {
                    "scale": scale,
                    "updates": [
                        {
                            "column": update.column,
                            "value": float(operating_point[update.column])
                            * math.exp(
                                scale
                                * math.log(
                                    update.value / float(operating_point[update.column])
                                )
                            ),
                            "canonical_key": update.canonical_key,
                        }
                        for update in projection.updates
                    ],
                }
            )
    return {
        "schema_version": "circuitpilot.transfer-projection.v1",
        "status": projection.status,
        "accepted": projection.accepted,
        "supported_effects": supported,
        "rejected_effects": rejected,
        "scenario_count": len(scenario_jacobians),
        "maximum_iterations": min(max(int(maximum_iterations), 1), 5),
        "projection": projection.as_dict(),
        "selected_parameters": selected_parameters,
        "dropped_parameters": dropped_parameters,
        "iteration_diagnostics": iterations,
        "trust_region_suggestions": suggestions,
        "evidence": dict(packet.evidence),
        "target_sensitivity_status": sensitivity.evidence_status,
        "ood_diagnostics": ood_diagnostics,
        "transfer_confidence": transfer_confidence,
    }


def _aggregate_scenario_jacobians(
    scenario_jacobians: Mapping[str, Mapping[str, Mapping[str, float]]],
    features: list[str],
    *,
    worst_scenario: str,
) -> dict[str, dict[str, float]]:
    aggregated: dict[str, dict[str, float]] = {}
    for feature in features:
        rows = [jacobian[feature] for jacobian in scenario_jacobians.values() if feature in jacobian]
        if not rows:
            continue
        parameters = sorted({name for row in rows for name in row})
        mean_row = {
            parameter: sum(float(row.get(parameter, 0.0)) for row in rows) / len(rows)
            for parameter in parameters
        }
        worst_row = scenario_jacobians.get(worst_scenario, {}).get(feature, {})
        aggregated[feature] = {
            parameter: 0.5 * mean_row[parameter] + 0.5 * float(worst_row.get(parameter, 0.0))
            for parameter in parameters
        }
    return aggregated


def _iterative_projection(
    *,
    target_effect: Mapping[str, float],
    scenario_jacobians: Mapping[str, Mapping[str, Mapping[str, float]]],
    features: list[str],
    profile: CircuitParameterProfile,
    operating_point: Mapping[str, Any],
    regularization: float,
    minimum_alignment: float,
    maximum_relative_residual: float,
    max_log_step: float,
    maximum_condition_number: float,
    normalized_uncertainty: float,
    maximum_normalized_uncertainty: float,
    maximum_iterations: int,
):
    scenario_names = sorted(scenario_jacobians)
    worst_scenario = scenario_names[0]
    diagnostics: list[dict[str, Any]] = []
    projection = None
    selected: list[str] = []
    dropped: list[str] = []
    for iteration in range(1, min(max(int(maximum_iterations), 1), 5) + 1):
        combined = _aggregate_scenario_jacobians(
            scenario_jacobians, features, worst_scenario=worst_scenario
        )
        reduced, selected, dropped, raw_rank, required_row_rank = _identifiable_subspace(
            combined, features, profile, operating_point
        )
        projection_jacobian = combined if raw_rank < required_row_rank else reduced
        projection = project_physical_effect(
            target_effect,
            projection_jacobian,
            profile,
            operating_point,
            regularization=regularization,
            minimum_alignment=minimum_alignment,
            maximum_relative_residual=maximum_relative_residual,
            max_log_step=max_log_step,
            reject_rank_deficient=True,
            maximum_condition_number=maximum_condition_number,
            normalized_uncertainty=normalized_uncertainty,
            maximum_normalized_uncertainty=maximum_normalized_uncertainty,
        )
        residuals = _scenario_residuals(
            projection, target_effect, scenario_jacobians, features, operating_point
        )
        new_worst = max(residuals, key=residuals.get) if residuals else worst_scenario
        diagnostics.append(
            {
                "iteration": iteration,
                "worst_scenario": worst_scenario,
                "scenario_residuals": residuals,
                "raw_rank": raw_rank,
                "required_row_rank": required_row_rank,
            }
        )
        if not projection.accepted or new_worst == worst_scenario:
            break
        worst_scenario = new_worst
    assert projection is not None
    return projection, selected, dropped, diagnostics


def _identifiable_subspace(
    jacobian: Mapping[str, Mapping[str, float]],
    features: list[str],
    profile: CircuitParameterProfile,
    operating_point: Mapping[str, Any],
) -> tuple[dict[str, dict[str, float]], list[str], list[str], int, int]:
    parameters = [
        parameter.column
        for parameter in profile.optimizable_parameters
        if parameter.column in operating_point
        and any(parameter.column in jacobian.get(feature, {}) for feature in features)
    ]
    matrix = np.asarray(
        [
            [float(jacobian.get(feature, {}).get(parameter, 0.0)) for parameter in parameters]
            for feature in features
        ],
        dtype=float,
    )
    raw_rank = int(np.linalg.matrix_rank(matrix)) if matrix.size else 0
    required_row_rank = min(len(features), len(parameters))
    if raw_rank < required_row_rank or len(parameters) <= len(features):
        return (
            {feature: dict(jacobian.get(feature, {})) for feature in features},
            parameters,
            [],
            raw_rank,
            required_row_rank,
        )
    norms = np.linalg.norm(matrix, axis=0)
    candidates = sorted(range(len(parameters)), key=lambda index: (-norms[index], parameters[index]))
    chosen: list[int] = []
    rank = 0
    for index in candidates:
        trial = matrix[:, [*chosen, index]]
        trial_rank = int(np.linalg.matrix_rank(trial))
        if trial_rank > rank:
            chosen.append(index)
            rank = trial_rank
        if rank == len(features):
            break
    selected = [parameters[index] for index in chosen]
    dropped = [parameter for parameter in parameters if parameter not in selected]
    reduced = {
        feature: {
            parameter: float(jacobian.get(feature, {}).get(parameter, 0.0))
            for parameter in selected
        }
        for feature in features
    }
    return reduced, selected, dropped, raw_rank, required_row_rank


def _scenario_residuals(
    projection,
    target_effect: Mapping[str, float],
    scenario_jacobians: Mapping[str, Mapping[str, Mapping[str, float]]],
    features: list[str],
    operating_point: Mapping[str, Any],
) -> dict[str, float]:
    if not projection.accepted:
        return {}
    deltas = {
        update.column: math.log(update.value / float(operating_point[update.column]))
        for update in projection.updates
    }
    residuals = {}
    for scenario, jacobian in scenario_jacobians.items():
        squared = 0.0
        for feature in features:
            realized = sum(
                float(jacobian.get(feature, {}).get(parameter, 0.0)) * delta
                for parameter, delta in deltas.items()
            )
            squared += (realized - float(target_effect[feature])) ** 2
        residuals[str(scenario)] = math.sqrt(squared)
    return residuals


def _assess_ood(
    packet: PhysicalEffectPacket,
    sensitivity: SensitivityArtifact,
    target_effect: Mapping[str, float],
) -> dict[str, Any]:
    if packet.schema_version != "circuitpilot.physical-effect.v1":
        return {
            "status": "out_of_distribution",
            "reason": "unsupported_physical_effect_protocol",
        }
    target_profiles = [
        str(value) for value in packet.applicability.get("target_profiles", [])
    ]
    if target_profiles and sensitivity.profile not in target_profiles:
        return {
            "status": "out_of_distribution",
            "reason": "target_profile_outside_declared_scope",
            "target_profile": sensitivity.profile,
            "declared_target_profiles": target_profiles,
        }
    effect_ranges = packet.applicability.get("effect_ranges", {}) or {}
    outside = {}
    for feature, value in target_effect.items():
        bounds = effect_ranges.get(feature)
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            continue
        lower, upper = float(bounds[0]), float(bounds[1])
        if value < lower or value > upper:
            outside[feature] = {"value": value, "bounds": [lower, upper]}
    if outside:
        return {
            "status": "out_of_distribution",
            "reason": "effect_outside_declared_range",
            "outside_effects": outside,
        }
    if not target_profiles and not effect_ranges:
        return {"status": "scope_not_declared", "reason": "diagnostic_only"}
    return {"status": "in_distribution", "reason": "declared_scope_match"}


def _transfer_confidence(
    packet: PhysicalEffectPacket,
    sensitivity: SensitivityArtifact,
    normalized_uncertainty: float,
    ood_diagnostics: Mapping[str, Any],
) -> float:
    source_factor = (
        1.0
        if packet.evidence.get("data_source") == "real_simulation_csv"
        else 0.7
    )
    target_factor = (
        1.0 if str(sensitivity.evidence_status).startswith("observed") else 0.7
    )
    uncertainty_factor = max(0.0, 1.0 - max(float(normalized_uncertainty), 0.0))
    scope_factor = {
        "in_distribution": 1.0,
        "scope_not_declared": 0.8,
        "out_of_distribution": 0.0,
    }.get(str(ood_diagnostics.get("status")), 0.0)
    return float(source_factor * target_factor * uncertainty_factor * scope_factor)


def _rejected(status: str, supported: list[str], rejected: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "circuitpilot.transfer-projection.v1",
        "status": status,
        "accepted": False,
        "supported_effects": supported,
        "rejected_effects": rejected,
        "scenario_count": 0,
        "maximum_iterations": 0,
        "projection": None,
        "trust_region_suggestions": [],
    }


def run_transfer_coordinator_agent(state: dict) -> dict:
    state["active_agent"] = "TransferCoordinatorAgent"
    inputs = state.get("inputs", {})
    source_packet = _load_mapping(inputs.get("source_effect_packet", {}))
    target_sensitivity = _load_mapping(
        inputs.get("target_sensitivity") or state.get("target_sensitivity") or {}
    )
    parameter_profile = inputs.get("parameter_profile") or state.get("parameter_profile")
    if parameter_profile is None and str(state.get("profile", "")).startswith(
        "instrumentation_amplifier"
    ):
        from goa_eval.instrumentation_amplifier import instrumentation_parameter_profile

        parameter_profile = instrumentation_parameter_profile()
    try:
        result = coordinate_transfer(
            source_packet,
            target_sensitivity or {},
            parameter_profile or {},
            inputs.get("operating_point", {}),
        )
    except (TypeError, ValueError, KeyError) as exc:
        result = _rejected("invalid_transfer_input", [], {"input": str(exc)})
    state["transfer_projection"] = result
    state["transfer_diagnostics"] = {
        "status": result["status"],
        "accepted": result["accepted"],
        "rejected_effects": result["rejected_effects"],
    }
    if state.get("output_dir"):
        output_dir = Path(state["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        projection_path = output_dir / "transfer_projection.json"
        projection_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.setdefault("generated_files", {})["transfer_projection"] = str(
            projection_path
        )
    add_message(state, "TransferCoordinatorAgent", {"transfer_projection": result})
    append_handoff(
        state,
        "TransferCoordinatorAgent",
        "CriticAgent",
        "transfer projection accepted" if result["accepted"] else "transfer projection rejected",
        ["transfer_projection", "transfer_diagnostics"],
    )
    return state


def _load_mapping(value: Any) -> Any:
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return value
