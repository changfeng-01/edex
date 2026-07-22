from __future__ import annotations

from pathlib import Path

import pandas as pd

from goa_eval.domain import CircuitParameterProfile, project_parameter_value
from goa_eval.multi_agent.agents._utils import add_message, store_tool_result
from goa_eval.multi_agent.handoff import append_handoff
from goa_eval.multi_agent.tools import (
    generate_candidates,
    inspect_candidates,
    inspect_optimization_history,
    inspect_optimization_leaderboard,
)


def run_optimization_agent(state: dict) -> dict:
    state["active_agent"] = "OptimizationAgent"
    inputs = state.get("inputs", {})
    transfer_projection = state.get("transfer_projection") or {}
    if transfer_projection.get("accepted") and transfer_projection.get(
        "trust_region_suggestions"
    ):
        return _run_transfer_projection(state, transfer_projection)
    existing_candidates = inputs.get("best_next_candidates") or inputs.get("next_candidates")
    if inputs.get("optimization_history"):
        result = inspect_optimization_history(inputs["optimization_history"])
        state["optimization_history_summary"] = result.data
        store_tool_result(state, "OptimizationAgent", result)
    if inputs.get("optimization_leaderboard") and not state.get("leaderboard_summary"):
        result = inspect_optimization_leaderboard(inputs["optimization_leaderboard"])
        state["leaderboard_summary"] = result.data
        store_tool_result(state, "OptimizationAgent", result)
    if existing_candidates:
        state["candidate_summary"] = _summarize_existing_candidates(existing_candidates, state)
        if inputs.get("param_space"):
            result = inspect_candidates(
                existing_candidates,
                inputs["param_space"],
                int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)),
            )
            state["candidate_summary"]["risk_summary"] = result.data
            store_tool_result(state, "OptimizationAgent", result)
        add_message(state, "OptimizationAgent", {"candidate_summary": state.get("candidate_summary")})
        append_handoff(
            state,
            "OptimizationAgent",
            "CriticAgent",
            "existing candidate artifact accepted",
            ["candidate_summary", "optimization_history_summary"],
        )
        return state
    leaderboard = inputs.get("leaderboard") or inputs.get("optimization_leaderboard")
    param_space = inputs.get("param_space")
    if not leaderboard or not param_space:
        state.setdefault("warnings", []).append("skip optimization: leaderboard or param_space missing")
        state["candidate_summary"] = {"candidate_count": 0, "skipped": True}
        add_message(state, "OptimizationAgent", {"skip_optimization": "leaderboard or param_space missing"})
        append_handoff(state, "OptimizationAgent", "CriticAgent", "optimization skipped", ["candidate_summary"])
        return state
    result = generate_candidates(leaderboard, param_space, state["output_dir"], int((state.get("limits") or {}).get("max_candidates", 10)))
    state["candidate_summary"] = result.data
    if result.data.get("next_candidates_path"):
        state.setdefault("generated_files", {})["next_candidates"] = result.data["next_candidates_path"]
    store_tool_result(state, "OptimizationAgent", result)
    candidate_path = result.data.get("next_candidates_path")
    if candidate_path and Path(candidate_path).exists():
        inspected = inspect_candidates(candidate_path, param_space, int((state.get("limits") or {}).get("max_parameter_changes_per_candidate", 2)))
        state["candidate_summary"]["risk_summary"] = inspected.data
        store_tool_result(state, "OptimizationAgent", inspected)
    add_message(state, "OptimizationAgent", {"candidate_summary": state.get("candidate_summary")})
    append_handoff(state, "OptimizationAgent", "CriticAgent", "candidate generation completed through optimizer wrapper", ["candidate_summary"])
    return state


def _summarize_existing_candidates(path_text: str | Path, state: dict) -> dict:
    path = Path(path_text)
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
    has_rerun = any((state.get("inputs") or {}).get(key) for key in ["rerun_run_dir", "rerun_leaderboard", "rerun_score_summary", "rerun_real_metrics"])
    return {
        "source": "existing_artifact",
        "status": "decision_ready" if has_rerun else "awaiting_rerun_results",
        "next_candidates_path": str(path),
        "candidate_count": int(len(frame)),
        "columns": list(frame.columns),
    }


def _run_transfer_projection(state: dict, transfer_projection: dict) -> dict:
    inputs = state.get("inputs", {})
    operating_point = dict(inputs.get("operating_point", {}) or {})
    raw_profile = inputs.get("parameter_profile") or state.get("parameter_profile")
    if isinstance(raw_profile, CircuitParameterProfile):
        profile = raw_profile
    elif raw_profile:
        profile = CircuitParameterProfile.from_mapping(raw_profile)
    elif str(state.get("profile", "")).startswith("instrumentation_amplifier"):
        from goa_eval.instrumentation_amplifier import instrumentation_parameter_profile

        profile = instrumentation_parameter_profile()
    else:
        state.setdefault("warnings", []).append(
            "skip transfer projection: parameter profile missing"
        )
        state["candidate_summary"] = {
            "source": "transfer_projection",
            "candidate_count": 0,
            "skipped": True,
        }
        return state
    specifications = {parameter.column: parameter for parameter in profile.optimizable_parameters}
    rows = []
    for suggestion in transfer_projection["trust_region_suggestions"]:
        candidate = dict(operating_point)
        changed: set[str] = set()
        for update in suggestion.get("updates", []):
            column = str(update.get("column", ""))
            if column not in specifications or column not in operating_point:
                continue
            candidate[column] = project_parameter_value(
                specifications[column], float(update["value"])
            )
            changed.add(column)
        if not _coupled_groups_satisfied(profile, changed):
            continue
        candidate["trust_region_scale"] = float(suggestion["scale"])
        candidate.update(_candidate_boundary(transfer_projection))
        _attach_barrier(state, candidate)
        rows.append(candidate)
    design_columns = [parameter.column for parameter in profile.optimizable_parameters]
    unique_rows = []
    seen = set()
    for row in rows:
        signature = tuple(row.get(column) for column in design_columns)
        if signature in seen:
            continue
        seen.add(signature)
        unique_rows.append(row)
    output_dir = Path(state.get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "next_candidates.csv"
    pd.DataFrame(unique_rows).to_csv(path, index=False)
    state.setdefault("generated_files", {})["next_candidates"] = str(path)
    state["candidate_summary"] = {
        "source": "transfer_projection",
        "status": "awaiting_rerun_results",
        "next_candidates_path": str(path),
        "candidate_count": len(unique_rows),
        "columns": list(pd.DataFrame(unique_rows).columns),
    }
    add_message(state, "OptimizationAgent", {"candidate_summary": state["candidate_summary"]})
    append_handoff(
        state,
        "OptimizationAgent",
        "CriticAgent",
        "transfer candidates projected, barrier-checked and deduplicated",
        ["candidate_summary", "transfer_projection"],
    )
    return state


def _candidate_boundary(transfer_projection: dict) -> dict:
    source_is_real = (
        (transfer_projection.get("evidence") or {}).get("data_source")
        == "real_simulation_csv"
    )
    sensitivity_is_observed = str(
        transfer_projection.get("target_sensitivity_status", "")
    ).startswith("observed")
    return {
        "data_source": (
            "real_simulation_csv"
            if source_is_real and sensitivity_is_observed
            else "analytic_model_proxy"
        ),
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }


def _attach_barrier(state: dict, candidate: dict) -> None:
    if not str(state.get("profile", "")).startswith("instrumentation_amplifier"):
        candidate["barrier_status"] = "not_available"
        return
    try:
        from goa_eval.instrumentation_amplifier import InstrumentationAmplifierPhysicsAdapter

        evaluated = InstrumentationAmplifierPhysicsAdapter().evaluate_scenario(
            candidate,
            {},
            objectives=state.get("objectives", {}),
            opamp_model=dict((state.get("inputs", {}) or {}).get("opamp_model", {}) or {}),
        )
        candidate["barrier"] = (evaluated.get("barrier") or {}).get("value")
        candidate["barrier_status"] = (evaluated.get("barrier") or {}).get(
            "status", "missing"
        )
    except (KeyError, TypeError, ValueError):
        candidate["barrier"] = None
        candidate["barrier_status"] = "missing"


def _coupled_groups_satisfied(
    profile: CircuitParameterProfile, changed: set[str]
) -> bool:
    for group, constraint in profile.group_constraints.items():
        if constraint not in {"keep_ratio", "must_change_together"}:
            continue
        columns = {
            parameter.column for parameter in profile.parameters if parameter.group == group
        }
        if changed.intersection(columns) and not columns <= changed:
            return False
    return True
