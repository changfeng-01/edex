from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import json
import random
from typing import Any

import pandas as pd
import yaml

from goa_eval.param_space import parse_engineering_value
from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


CANDIDATE_COLUMNS = [
    "schema_version",
    "result_version",
    "candidate_id",
    "priority",
    "parameter",
    "direction",
    "candidate_value",
    "candidate_unit",
    "source_recommendation",
    "trigger_metric",
    "data_source",
    "engineering_validity",
    "strategy",
    "candidate_kind",
    "changed_parameters",
    "parameters_json",
    "search_score",
    "rationale",
]


@dataclass(frozen=True)
class OptimizationRequest:
    parameter_space: dict[str, Any]
    objective: str = "overall_score"
    constraints: dict[str, Any] | None = None


@dataclass(frozen=True)
class OptimizationResult:
    status: str
    best_parameters: dict[str, Any] | None
    message: str


class CircuitPilotOptimizer:
    """Placeholder interface for future optimization algorithms."""

    def optimize(self, request: OptimizationRequest) -> OptimizationResult:
        raise NotImplementedError("CircuitPilot optimizer is not implemented in this prototype.")


def load_param_space(path: Path) -> dict[str, list[object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", raw)
    loaded = {}
    for key, value in parameters.items():
        if isinstance(value, dict) and "values" in value:
            values = value.get("values", [])
            loaded[key] = {
                "unit": value.get("unit", ""),
                "values": list(values) if isinstance(values, list) else [values],
            }
        else:
            loaded[key] = list(value) if isinstance(value, list) else [value]
    return loaded


def load_baseline_params(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(raw.get("parameters", raw) or {})


def propose_candidates(param_space: dict[str, list[object]], recommendations: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for recommendation in recommendations:
        rec_id = str(recommendation.get("recommendation_id", ""))
        metric = str(recommendation.get("trigger_metric", ""))
        if "ripple" in rec_id or metric == "Max_ripple":
            _append_if_available(candidates, param_space, "C_store", "increase", 90, recommendation)
            _append_if_available(candidates, param_space, "capacitance", "increase", 90, recommendation)
            _append_if_available(candidates, param_space, "load_cap", "review", 60, recommendation)
        if "delay" in rec_id or metric == "Delay_mean":
            _append_if_available(candidates, param_space, "R_driver", "decrease", 80, recommendation)
            _append_if_available(candidates, param_space, "drive_resistance", "decrease", 80, recommendation)
            _append_if_available(candidates, param_space, "W_nmos", "increase", 70, recommendation)
            _append_if_available(candidates, param_space, "W_pmos", "increase", 70, recommendation)
            _append_if_available(candidates, param_space, "transistor_width", "increase", 70, recommendation)
        if "overlap" in rec_id or metric == "Max_overlap_ratio":
            _append_if_available(candidates, param_space, "R_driver", "review_timing", 85, recommendation)
            _append_if_available(candidates, param_space, "drive_resistance", "review_timing", 85, recommendation)
        if "false_trigger" in rec_id or metric == "FalseTriggerCount":
            _append_if_available(candidates, param_space, "VDD", "review_threshold", 75, recommendation)
            _append_if_available(candidates, param_space, "vdd", "review_threshold", 75, recommendation)
    return candidates


def constrained_random_candidates(
    param_space: dict[str, list[object]],
    recommendations: list[dict],
    *,
    max_candidates: int = 10,
    seed: int = 42,
    baseline_params: dict[str, object] | None = None,
) -> list[dict]:
    baseline_params = baseline_params or {}
    rule_candidates = [
        candidate
        for candidate in propose_candidates(param_space, recommendations)
        if _matches_direction(candidate, baseline_params)
    ]
    single_candidates = [_search_candidate([candidate], "single_parameter") for candidate in rule_candidates]
    combo_candidates = [
        _search_candidate(list(pair), "two_parameter_combo")
        for pair in combinations(rule_candidates, 2)
        if pair[0]["parameter"] != pair[1]["parameter"]
    ]
    candidates = single_candidates + combo_candidates
    rng = random.Random(seed)
    for candidate in candidates:
        candidate["_random_rank"] = rng.random()
    ranked = sorted(
        candidates,
        key=lambda item: (
            -float(item.get("search_score", 0)),
            float(item.get("_random_rank", 0)),
            str(item.get("candidate_kind", "")),
            str(item.get("changed_parameters", "")),
        ),
    )
    return [
        {key: value for key, value in candidate.items() if key != "_random_rank"}
        for candidate in ranked[: max(0, int(max_candidates))]
    ]


def rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(
        candidates,
        key=lambda item: (
            -float(item.get("priority", 0)),
            str(item.get("parameter", "")),
            str(item.get("candidate_value", "")),
        ),
    )


def _append_if_available(candidates: list[dict], param_space: dict[str, list[object]], parameter: str, direction: str, priority: int, recommendation: dict) -> None:
    if parameter not in param_space:
        return
    values, unit = _values_and_unit(param_space[parameter])
    for value in values:
        candidates.append(
            {
                "schema_version": SCHEMA_VERSION,
                "result_version": RESULT_VERSION,
                "parameter": parameter,
                "direction": direction,
                "candidate_value": value,
                "candidate_unit": unit,
                "priority": priority,
                "source_recommendation": recommendation.get("recommendation_id"),
                "trigger_metric": recommendation.get("trigger_metric"),
                "data_source": recommendation.get("data_source", "real_simulation_csv"),
                "engineering_validity": recommendation.get("engineering_validity", "simulation_only"),
                "strategy": "rule",
                "candidate_kind": "single_parameter",
                "changed_parameters": parameter,
                "parameters_json": {parameter: value},
                "search_score": priority,
                "rationale": f"{parameter} {direction} from {recommendation.get('recommendation_id')}",
            }
        )


def write_candidate_outputs(candidates: list[dict], *, csv_path: Path, markdown_path: Path) -> None:
    rows = _rows_with_ids(rank_candidates(candidates))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=CANDIDATE_COLUMNS).to_csv(csv_path, index=False, encoding="utf-8-sig")
    markdown_path.write_text(_candidate_markdown(rows), encoding="utf-8")


def _rows_with_ids(candidates: list[dict]) -> list[dict]:
    rows = []
    for index, candidate in enumerate(candidates, start=1):
        row = {column: candidate.get(column, "") for column in CANDIDATE_COLUMNS}
        row["schema_version"] = row["schema_version"] or SCHEMA_VERSION
        row["result_version"] = row["result_version"] or RESULT_VERSION
        row["candidate_id"] = row["candidate_id"] or f"cand_{index:03d}"
        row["data_source"] = row["data_source"] or "real_simulation_csv"
        row["engineering_validity"] = row["engineering_validity"] or "simulation_only"
        row["strategy"] = row["strategy"] or "rule"
        row["candidate_kind"] = row["candidate_kind"] or "single_parameter"
        row["changed_parameters"] = row["changed_parameters"] or row["parameter"]
        row["parameters_json"] = _json_cell(row["parameters_json"] or {row["parameter"]: row["candidate_value"]})
        row["search_score"] = row["search_score"] if row["search_score"] != "" else row["priority"]
        row["rationale"] = row["rationale"] or f"{row['parameter']} {row['direction']}"
        rows.append(row)
    return rows


def _candidate_markdown(rows: list[dict]) -> str:
    lines = [
        "# CircuitPilot 下一轮参数候选",
        "",
        f"- schema_version: `{SCHEMA_VERSION}`",
        f"- result_version: `{RESULT_VERSION}`",
        "- data_source: `real_simulation_csv`",
        "- engineering_validity: `simulation_only`",
        "",
        "本报告基于仿真 CSV 的结构化指标和规则建议生成，不是实物测试结果，也不表示自动优化闭环已经完成。",
        "候选项按约束、规则优先级和搜索得分排序；constrained_random 策略只生成单参数和两参数组合候选。",
        "",
        "## Candidates",
        "",
    ]
    if not rows:
        lines.extend(["当前规则没有生成可行动参数候选。", ""])
        return "\n".join(lines)
    for row in rows:
        value = row["candidate_value"]
        unit = row["candidate_unit"]
        value_text = f"{value} {unit}".strip()
        lines.extend(
            [
                f"### {row['candidate_id']}",
                "",
                f"- priority: `{row['priority']}`",
                f"- strategy: `{row['strategy']}`",
                f"- candidate_kind: `{row['candidate_kind']}`",
                f"- parameter: `{row['parameter']}`",
                f"- direction: `{row['direction']}`",
                f"- candidate_value: `{value_text}`",
                f"- changed_parameters: `{row['changed_parameters']}`",
                f"- search_score: `{row['search_score']}`",
                f"- source_recommendation: `{row['source_recommendation']}`",
                f"- trigger_metric: `{row['trigger_metric']}`",
                f"- rationale: {row['rationale']}",
                "",
            ]
        )
    return "\n".join(lines)


def _values_and_unit(entry) -> tuple[list[object], str]:
    if isinstance(entry, dict):
        values = entry.get("values", [])
        unit = str(entry.get("unit", "") or "")
        return (list(values) if isinstance(values, list) else [values], unit)
    return (list(entry) if isinstance(entry, list) else [entry], "")


def _search_candidate(parts: list[dict], kind: str) -> dict:
    parameters = {part["parameter"]: part["candidate_value"] for part in parts}
    changed = sorted(parameters)
    priority = max(float(part.get("priority", 0)) for part in parts)
    combo_penalty = 0.0 if kind == "single_parameter" else 5.0
    search_score = priority - combo_penalty
    primary = parts[0]
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "candidate_id": "",
        "priority": int(priority),
        "parameter": ";".join(changed),
        "direction": ";".join(str(part.get("direction", "")) for part in parts),
        "candidate_value": primary.get("candidate_value", ""),
        "candidate_unit": primary.get("candidate_unit", ""),
        "source_recommendation": ";".join(str(part.get("source_recommendation", "")) for part in parts),
        "trigger_metric": ";".join(str(part.get("trigger_metric", "")) for part in parts),
        "data_source": primary.get("data_source", "real_simulation_csv"),
        "engineering_validity": primary.get("engineering_validity", "simulation_only"),
        "strategy": "constrained_random",
        "candidate_kind": kind,
        "changed_parameters": ";".join(changed),
        "parameters_json": parameters,
        "search_score": search_score,
        "rationale": _rationale(parts, kind),
    }


def _matches_direction(candidate: dict, baseline_params: dict[str, object]) -> bool:
    parameter = str(candidate.get("parameter", ""))
    if parameter not in baseline_params:
        return True
    baseline = _numeric_value(baseline_params.get(parameter))
    value = _numeric_value(candidate.get("candidate_value"))
    if baseline is None or value is None:
        return True
    direction = str(candidate.get("direction", ""))
    if direction == "increase":
        return value > baseline
    if direction == "decrease":
        return value < baseline
    return value != baseline


def _numeric_value(value) -> float | None:
    parsed = parse_engineering_value(value)
    if parsed is not None:
        return parsed
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rationale(parts: list[dict], kind: str) -> str:
    labels = [f"{part.get('parameter')} {part.get('direction')}" for part in parts]
    prefix = "single-parameter" if kind == "single_parameter" else "two-parameter"
    return f"{prefix} constrained candidate from rule triggers: {', '.join(labels)}"


def _json_cell(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
