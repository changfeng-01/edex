from __future__ import annotations

from pathlib import Path
import json
import random
import shutil
from typing import Any

import pandas as pd
import yaml

from goa_eval.sky130_sweep import run_sky130_sweep


def build_adaptive_sweep_config(
    *,
    base_config: dict,
    history: pd.DataFrame,
    best_run_dir: Path | None,
    max_runs: int,
    seed: int = 42,
    exploration_ratio: float = 0.25,
) -> dict:
    parameters = dict(base_config.get("parameters", {}) or {})
    baseline = _best_parameter_row(history, parameters)
    seen = _seen_points(history, parameters)
    points: list[dict[str, object]] = []

    for candidate in _candidate_points(best_run_dir, baseline):
        _append_unique_point(points, candidate, parameters, seen, max_runs)

    exploration_count = max(0, int(round(max_runs * max(0.0, min(1.0, exploration_ratio)))))
    exploration_pool = _all_points(parameters)
    random.Random(seed).shuffle(exploration_pool)
    for point in exploration_pool:
        if len(points) >= max_runs or len(points) >= max_runs - exploration_count:
            break
        _append_unique_point(points, point, parameters, seen, max_runs)
    for point in exploration_pool:
        _append_unique_point(points, point, parameters, seen, max_runs)
        if len(points) >= max_runs:
            break

    config = {key: value for key, value in base_config.items() if key != "points"}
    config["parameters"] = parameters
    config["points"] = points
    return {
        "config": config,
        "points": points,
        "stop_reason": "" if points else "no new sweep points",
    }


def should_stop_optimization(rounds: list[dict], *, patience: int, min_improvement: float) -> str:
    if len(rounds) <= 1 or patience <= 0:
        return ""
    best = _as_float(rounds[0].get("best_score"))
    stale = 0
    for item in rounds[1:]:
        score = _as_float(item.get("best_score"))
        if score is None:
            stale += 1
        elif best is None or score >= best + min_improvement:
            best = score
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            return f"no improvement for {patience} round(s)"
    return ""


def run_multi_round_optimization(
    *,
    sweep_path: Path,
    output_root: Path,
    rounds: int,
    max_runs_per_round: int,
    patience: int = 2,
    min_improvement: float = 0.0,
    exploration_ratio: float = 0.25,
    pdk_root: Path | None = None,
    split: str = "train",
    max_rows: int = 5,
    topology: str | None = None,
    source_dataset: str | None = None,
    dataset_name: str = "pphilip/analog-circuits-sky130",
    mock_dataset_json: Path | None = None,
    mock_ngspice: bool = False,
    ngspice_cmd: str = "ngspice",
    spec_path: Path = Path("config/sky130_transient_spec.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    max_candidates: int = 10,
    seed: int = 42,
) -> list[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    base_config = yaml.safe_load(sweep_path.read_text(encoding="utf-8")) or {}
    history_rows: list[dict] = []
    round_rows: list[dict] = []
    current_config = base_config
    best_score: float | None = None
    best_run_dir: Path | None = None

    for round_index in range(1, max(0, rounds) + 1):
        round_dir = output_root / f"round_{round_index:03d}"
        round_sweep_path = output_root / f"round_{round_index:03d}_sweep.yaml"
        round_sweep_path.write_text(yaml.safe_dump(current_config, sort_keys=False, allow_unicode=True), encoding="utf-8")
        summaries = run_sky130_sweep(
            sweep_path=round_sweep_path,
            output_root=round_dir,
            pdk_root=pdk_root,
            split=split,
            max_rows=max_rows,
            topology=topology,
            source_dataset=source_dataset,
            dataset_name=dataset_name,
            mock_dataset_json=mock_dataset_json,
            mock_ngspice=mock_ngspice,
            ngspice_cmd=ngspice_cmd,
            spec_path=spec_path,
            param_space_path=param_space_path,
            max_candidates=max_candidates,
            seed=seed + round_index - 1,
            max_runs=max_runs_per_round,
        )
        for row in summaries:
            absolute_run_dir = round_dir / str(row.get("run_dir", ""))
            history_rows.append({"round_index": round_index, **row, "run_dir": str(absolute_run_dir)})

        history = pd.DataFrame(history_rows)
        best = _best_history_row(history)
        if best is not None:
            best_score = _as_float(best.get("overall_score"))
            best_run_dir = Path(str(best.get("run_dir")))

        stop_reason = should_stop_optimization(
            [*round_rows, {"round_index": round_index, "best_score": best_score}],
            patience=patience,
            min_improvement=min_improvement,
        )
        round_rows.append(
            {
                "round_index": round_index,
                "run_count": len(summaries),
                "best_score": best_score,
                "best_run_dir": str(best_run_dir) if best_run_dir else "",
                "stop_reason": stop_reason,
            }
        )
        if stop_reason or round_index == rounds:
            break
        adaptive = build_adaptive_sweep_config(
            base_config=base_config,
            history=history,
            best_run_dir=best_run_dir,
            max_runs=max_runs_per_round,
            seed=seed + round_index,
            exploration_ratio=exploration_ratio,
        )
        current_config = adaptive["config"]
        if adaptive["stop_reason"]:
            round_rows[-1]["stop_reason"] = adaptive["stop_reason"]
            break

    _write_multi_round_outputs(output_root, history_rows, round_rows, current_config, best_run_dir)
    return round_rows


def _write_multi_round_outputs(
    output_root: Path,
    history_rows: list[dict],
    round_rows: list[dict],
    final_config: dict,
    best_run_dir: Path | None,
) -> None:
    (output_root / "optimization_history.json").write_text(
        json.dumps({"rounds": round_rows, "history": history_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(round_rows).to_csv(output_root / "round_summary.csv", index=False, encoding="utf-8-sig")
    leaderboard = pd.DataFrame(history_rows)
    if not leaderboard.empty:
        scores = pd.to_numeric(leaderboard.get("overall_score"), errors="coerce").fillna(float("-inf"))
        leaderboard = leaderboard.assign(_score=scores).sort_values("_score", ascending=False).drop(columns=["_score"])
    leaderboard.to_csv(output_root / "optimization_leaderboard.csv", index=False, encoding="utf-8-sig")
    (output_root / "final_param_space.yaml").write_text(
        yaml.safe_dump(final_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    best_candidates = best_run_dir / "next_candidates.csv" if best_run_dir else None
    target = output_root / "best_next_candidates.csv"
    if best_candidates is not None and best_candidates.exists():
        shutil.copyfile(best_candidates, target)
    else:
        pd.DataFrame().to_csv(target, index=False, encoding="utf-8-sig")


def _candidate_points(best_run_dir: Path | None, baseline: dict[str, object]) -> list[dict[str, object]]:
    if best_run_dir is None:
        return []
    path = best_run_dir / "next_candidates.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    if "search_score" in frame:
        frame["_score"] = pd.to_numeric(frame["search_score"], errors="coerce").fillna(0)
        frame = frame.sort_values("_score", ascending=False)
    points: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        changes = _candidate_change_dict(row)
        if not changes:
            continue
        points.append({**baseline, **changes})
    return points


def _candidate_change_dict(row: pd.Series) -> dict[str, object]:
    raw = row.get("parameters_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    parameter = row.get("parameter")
    if parameter is None or pd.isna(parameter):
        return {}
    return {str(parameter): row.get("candidate_value")}


def _best_parameter_row(history: pd.DataFrame, parameters: dict[str, Any]) -> dict[str, object]:
    best = _best_history_row(history)
    if best is None:
        return {name: _values(spec)[0] for name, spec in parameters.items() if _values(spec)}
    baseline: dict[str, object] = {}
    for name, spec in parameters.items():
        value = best.get(name)
        if value is None or pd.isna(value):
            values = _values(spec)
            value = values[0] if values else ""
        baseline[name] = value
    return baseline


def _best_history_row(history: pd.DataFrame) -> dict | None:
    if history.empty or "overall_score" not in history:
        return None
    scores = pd.to_numeric(history["overall_score"], errors="coerce")
    if not scores.notna().any():
        return None
    eligible = history.copy()
    eligible["_score"] = scores
    if "status" in eligible:
        evaluated = eligible[eligible["status"].eq("evaluated")]
        if not evaluated.empty and pd.to_numeric(evaluated["_score"], errors="coerce").notna().any():
            eligible = evaluated
    row = eligible.sort_values("_score", ascending=False).iloc[0].drop(labels=["_score"], errors="ignore")
    return row.to_dict()


def _seen_points(history: pd.DataFrame, parameters: dict[str, Any]) -> set[tuple]:
    seen = set()
    for _, row in history.iterrows():
        point = tuple(row.get(name) for name in parameters)
        if any(value is None or pd.isna(value) for value in point):
            continue
        seen.add(point)
    return seen


def _append_unique_point(
    points: list[dict[str, object]],
    point: dict[str, object],
    parameters: dict[str, Any],
    seen: set[tuple],
    max_runs: int,
) -> None:
    normalized = {name: point[name] for name in parameters if name in point}
    if len(normalized) != len(parameters):
        return
    key = tuple(normalized[name] for name in parameters)
    existing = {tuple(item[name] for name in parameters) for item in points}
    if key in seen or key in existing or len(points) >= max_runs:
        return
    points.append(normalized)


def _all_points(parameters: dict[str, Any]) -> list[dict[str, object]]:
    if not parameters:
        return []
    names = list(parameters)
    points = [{}]
    for name in names:
        values = _values(parameters[name])
        points = [{**point, name: value} for point in points for value in values]
    return points


def _values(spec: Any) -> list[object]:
    if isinstance(spec, dict):
        values = spec.get("values", [])
        return list(values) if isinstance(values, list) else [values]
    return list(spec) if isinstance(spec, list) else [spec]


def _as_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
