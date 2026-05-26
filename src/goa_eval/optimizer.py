from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class OptimizationRequest:
    parameter_space: dict[str, Any]
    objective: str = "overall_score"
    constraints: dict[str, Any] | None = None
    history: list[dict[str, Any]] | None = None
    max_candidates: int = 10


@dataclass(frozen=True)
class OptimizationResult:
    status: str
    best_parameters: dict[str, Any] | None
    message: str
    best_run_id: str | None = None
    next_candidates: list[dict[str, Any]] | None = None


class CircuitPilotOptimizer:
    """Conservative closed-loop optimizer over evaluated simulation runs."""

    def optimize(self, request: OptimizationRequest) -> OptimizationResult:
        history = pd.DataFrame(request.history or [])
        if history.empty:
            return OptimizationResult(status="no_history", best_parameters=None, message="No evaluated runs were provided.", next_candidates=[])
        param_space = normalize_param_space(request.parameter_space)
        leaderboard = rank_optimization_leaderboard(history)
        candidates = generate_next_round_candidates(
            param_space=param_space,
            leaderboard=leaderboard,
            max_candidates=request.max_candidates,
        )
        best = leaderboard.iloc[0].to_dict()
        parameter_names = set(param_space)
        best_parameters = {key: best[key] for key in parameter_names if key in best and pd.notna(best[key])}
        return OptimizationResult(
            status="ok",
            best_parameters=best_parameters,
            message=f"Selected {best.get('run_id', 'best run')} and generated {len(candidates)} next-round candidates.",
            best_run_id=str(best.get("run_id")) if best.get("run_id") is not None else None,
            next_candidates=candidates,
        )


def load_param_space(path: Path) -> dict[str, list[object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", raw)
    return normalize_param_space(parameters)


def normalize_param_space(parameters: dict[str, Any]) -> dict[str, list[object]]:
    loaded: dict[str, list[object]] = {}
    for key, value in parameters.items():
        if isinstance(value, dict) and "values" in value:
            values = value["values"]
        else:
            values = value
        loaded[key] = list(values) if isinstance(values, list) else [values]
    return loaded


def propose_candidates(param_space: dict[str, list[object]], recommendations: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for recommendation in recommendations:
        rec_id = str(recommendation.get("recommendation_id", ""))
        metric = str(recommendation.get("trigger_metric", ""))
        if "ripple" in rec_id or metric == "Max_ripple":
            _append_if_available(candidates, param_space, "C_store", "increase", 90, recommendation)
            _append_if_available(candidates, param_space, "load_cap", "review", 60, recommendation)
        if "delay" in rec_id or metric == "Delay_mean":
            _append_if_available(candidates, param_space, "R_driver", "decrease", 80, recommendation)
            _append_if_available(candidates, param_space, "W_nmos", "increase", 70, recommendation)
            _append_if_available(candidates, param_space, "W_pmos", "increase", 70, recommendation)
        if "overlap" in rec_id or metric == "Max_overlap_ratio":
            _append_if_available(candidates, param_space, "R_driver", "review_timing", 85, recommendation)
        if "false_trigger" in rec_id or metric == "FalseTriggerCount":
            _append_if_available(candidates, param_space, "VDD", "review_threshold", 75, recommendation)
    return candidates


def rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda item: (-float(item.get("priority", 0)), str(item.get("parameter", ""))))


def rank_optimization_leaderboard(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return leaderboard.copy()
    ranked = leaderboard.copy()
    if "hard_constraint_passed" not in ranked:
        ranked["hard_constraint_passed"] = False
    if "overall_score" not in ranked:
        ranked["overall_score"] = 0.0
    ranked["_hard_rank"] = ranked["hard_constraint_passed"].map(_truthy).astype(int)
    ranked["_overall_rank"] = pd.to_numeric(ranked["overall_score"], errors="coerce").fillna(-1.0)
    sort_cols = ["_hard_rank", "_overall_rank"]
    ascending = [False, False]
    if "run_id" in ranked:
        sort_cols.append("run_id")
        ascending.append(True)
    ranked = ranked.sort_values(sort_cols, ascending=ascending).drop(columns=["_hard_rank", "_overall_rank"])
    ranked["optimization_rank"] = range(1, len(ranked) + 1)
    return ranked


def generate_next_round_candidates(*, param_space: dict[str, list[object]], leaderboard: pd.DataFrame, max_candidates: int = 10) -> list[dict[str, Any]]:
    if leaderboard.empty or not param_space or max_candidates <= 0:
        return []
    ranked = rank_optimization_leaderboard(leaderboard)
    source = ranked.iloc[0].to_dict()
    base_params = _base_parameters(source, param_space)
    if not base_params:
        return []

    candidates: list[dict[str, Any]] = []
    single_changes: list[tuple[str, object, dict[str, Any]]] = []
    for parameter in sorted(param_space):
        if parameter not in base_params:
            continue
        for value in _neighbor_values(param_space[parameter], base_params[parameter]):
            params = dict(base_params)
            params[parameter] = value
            single_changes.append((parameter, value, params))
            candidates.append(
                _candidate_row(
                    index=len(candidates) + 1,
                    source=source,
                    params=params,
                    changed=[parameter],
                    kind="single_parameter",
                    rationale=f"Change {parameter} from {base_params[parameter]} to {value} around the current best run.",
                )
            )
            if len(candidates) >= max_candidates:
                return candidates
            break

    for left_index, (left_param, _left_value, left_params) in enumerate(single_changes):
        for right_param, right_value, _right_params in single_changes[left_index + 1 :]:
            if left_param == right_param:
                continue
            params = dict(left_params)
            params[right_param] = right_value
            candidates.append(
                _candidate_row(
                    index=len(candidates) + 1,
                    source=source,
                    params=params,
                    changed=[left_param, right_param],
                    kind="two_parameter_combo",
                    rationale=f"Combine local changes in {left_param} and {right_param} from the current best run.",
                )
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def write_closed_loop_outputs(*, leaderboard_path: Path, param_space_path: Path, output_dir: Path, max_candidates: int = 10) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    leaderboard = pd.read_csv(leaderboard_path)
    ranked = rank_optimization_leaderboard(leaderboard)
    param_space = load_param_space(param_space_path)
    candidates = generate_next_round_candidates(param_space=param_space, leaderboard=ranked, max_candidates=max_candidates)

    ranked_path = output_dir / "optimization_leaderboard.csv"
    candidates_path = output_dir / "next_candidates.csv"
    report_path = output_dir / "next_candidates.md"
    history_path = output_dir / "optimization_history.json"

    ranked.to_csv(ranked_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(candidates).to_csv(candidates_path, index=False, encoding="utf-8-sig")
    history_path.write_text(
        json.dumps(
            {
                "leaderboard_path": str(leaderboard_path),
                "param_space_path": str(param_space_path),
                "candidate_count": len(candidates),
                "engineering_validity": "simulation_only",
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_path.write_text(_candidate_report(candidates, leaderboard_path, param_space_path), encoding="utf-8")
    return {
        "optimization_leaderboard": ranked_path,
        "next_candidates": candidates_path,
        "next_candidates_report": report_path,
        "optimization_history": history_path,
    }


def _append_if_available(candidates: list[dict], param_space: dict[str, list[object]], parameter: str, direction: str, priority: int, recommendation: dict) -> None:
    if parameter not in param_space:
        return
    candidates.append(
        {
            "parameter": parameter,
            "direction": direction,
            "candidate_values": param_space.get(parameter, []),
            "priority": priority,
            "source_recommendation": recommendation.get("recommendation_id"),
            "trigger_metric": recommendation.get("trigger_metric"),
        }
    )


def _base_parameters(source: dict[str, Any], param_space: dict[str, list[object]]) -> dict[str, Any]:
    base: dict[str, Any] = {}
    for key, values in param_space.items():
        if key in source and pd.notna(source[key]):
            base[key] = _coerce_like(source[key], values)
        elif values:
            base[key] = values[0]
    return base


def _neighbor_values(values: list[object], current: object) -> list[object]:
    if not values:
        return []
    current_text = str(current)
    matches = [index for index, value in enumerate(values) if str(value) == current_text]
    if not matches:
        return [value for value in values if str(value) != current_text]
    index = matches[0]
    ordered: list[object] = []
    for neighbor in (index + 1, index - 1):
        if 0 <= neighbor < len(values):
            ordered.append(values[neighbor])
    for value in values:
        if str(value) != current_text and value not in ordered:
            ordered.append(value)
    return ordered


def _candidate_row(*, index: int, source: dict[str, Any], params: dict[str, Any], changed: list[str], kind: str, rationale: str) -> dict[str, Any]:
    return {
        "candidate_id": f"cand_{index:03d}",
        "candidate_kind": kind,
        "source_run_id": source.get("run_id"),
        "source_overall_score": source.get("overall_score"),
        "source_hard_constraint_passed": source.get("hard_constraint_passed"),
        "changed_parameters": ",".join(changed),
        "parameters_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
        "acquisition_score": _acquisition_score(source, changed),
        "rationale": rationale,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        **params,
    }


def _acquisition_score(source: dict[str, Any], changed: list[str]) -> float:
    base = _float(source.get("overall_score"), 0.0)
    hard_bonus = 10.0 if _truthy(source.get("hard_constraint_passed")) else 0.0
    exploration_bonus = min(6.0, 2.0 * len(changed))
    return round(base + hard_bonus + exploration_bonus, 6)


def _candidate_report(candidates: list[dict[str, Any]], leaderboard_path: Path, param_space_path: Path) -> str:
    lines = [
        "# CircuitPilot Next-Round Candidates",
        "",
        f"- leaderboard: `{leaderboard_path}`",
        f"- parameter_space: `{param_space_path}`",
        "- data_source: `real_simulation_csv`",
        "- engineering_validity: `simulation_only`",
        "",
        "These candidates are next-run proposals derived from prior simulation CSV results. They are not physical validation results and do not by themselves complete optimization.",
        "",
    ]
    for candidate in candidates:
        lines.extend(
            [
                f"## {candidate['candidate_id']}",
                "",
                f"- kind: `{candidate['candidate_kind']}`",
                f"- source_run_id: `{candidate.get('source_run_id')}`",
                f"- changed_parameters: `{candidate['changed_parameters']}`",
                f"- acquisition_score: `{candidate['acquisition_score']}`",
                f"- parameters_json: `{candidate['parameters_json']}`",
                f"- rationale: {candidate['rationale']}",
                "",
            ]
        )
    return "\n".join(lines)


def _coerce_like(value: object, values: list[object]) -> object:
    value_text = str(value)
    for candidate in values:
        if str(candidate) == value_text:
            return candidate
    return value


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
