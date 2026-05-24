from __future__ import annotations

from pathlib import Path
import json
import random
import shutil
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

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
    point_metadata: list[dict[str, object]] = []

    for candidate, metadata in _candidate_points(best_run_dir, baseline):
        _append_unique_point(points, point_metadata, candidate, metadata, parameters, seen, max_runs)

    exploration_count = max(0, int(round(max_runs * max(0.0, min(1.0, exploration_ratio)))))
    exploration_pool = _all_points(parameters)
    random.Random(seed).shuffle(exploration_pool)
    for point in exploration_pool:
        if len(points) >= max_runs or len(points) >= max_runs - exploration_count:
            break
        _append_unique_point(points, point_metadata, point, _source_metadata("exploration"), parameters, seen, max_runs)
    for point in exploration_pool:
        _append_unique_point(points, point_metadata, point, _source_metadata("exploration"), parameters, seen, max_runs)
        if len(points) >= max_runs:
            break

    config = {key: value for key, value in base_config.items() if key != "points"}
    config["parameters"] = parameters
    config["points"] = points
    config["point_metadata"] = point_metadata
    return {
        "config": config,
        "points": points,
        "stop_reason": "" if points else "no new sweep points",
    }


def build_strategy_sweep_config(
    *,
    base_config: dict,
    history: pd.DataFrame,
    best_run_dir: Path | None,
    max_runs: int,
    seed: int = 42,
    exploration_ratio: float = 0.25,
    strategy: str = "adaptive",
) -> dict:
    if strategy == "adaptive":
        result = build_adaptive_sweep_config(
            base_config=base_config,
            history=history,
            best_run_dir=best_run_dir,
            max_runs=max_runs,
            seed=seed,
            exploration_ratio=exploration_ratio,
        )
        result["config"]["optimizer_strategy"] = "adaptive"
        for metadata in result["config"].get("point_metadata", []):
            metadata.setdefault("optimizer_strategy", "adaptive")
            metadata.setdefault("objective_score", "")
            metadata.setdefault("model_status", "not_used")
        return result

    parameters = dict(base_config.get("parameters", {}) or {})
    seen = _seen_points(history, parameters)
    grid = [point for point in _all_points(parameters) if _point_key(point, parameters) not in seen]
    points: list[dict[str, object]] = []
    point_metadata: list[dict[str, object]] = []
    rng = random.Random(seed)

    if strategy in {"hybrid", "genetic"}:
        for candidate, metadata in _candidate_points(best_run_dir, _best_parameter_row(history, parameters)):
            metadata = {**metadata, "optimizer_strategy": strategy, "model_status": "rule_seed"}
            _append_unique_point(points, point_metadata, candidate, metadata, parameters, seen, max_runs)

    if strategy in {"genetic", "hybrid"} and len(points) < max_runs:
        for point, metadata in _genetic_points(parameters, history, max_runs=max_runs, seed=seed):
            metadata["optimizer_strategy"] = strategy
            _append_unique_point(points, point_metadata, point, metadata, parameters, seen, max_runs)

    if strategy in {"bayesian", "surrogate", "hybrid"} and len(points) < max_runs:
        ranked_model_points = _model_ranked_points(parameters, history, grid, strategy=strategy, seed=seed)
        for point, metadata in ranked_model_points:
            metadata["optimizer_strategy"] = strategy
            _append_unique_point(points, point_metadata, point, metadata, parameters, seen, max_runs)

    if len(points) < max_runs:
        model_status = _fallback_reason(history)
        for point in _diverse_points(parameters, history, grid, seed=seed):
            metadata = _source_metadata(
                "diversity_fallback",
                optimizer_strategy=strategy,
                model_status=model_status,
                objective_score="",
            )
            _append_unique_point(points, point_metadata, point, metadata, parameters, seen, max_runs)
            if len(points) >= max_runs:
                break

    config = {key: value for key, value in base_config.items() if key not in {"points", "point_metadata"}}
    config["parameters"] = parameters
    config["points"] = points
    config["point_metadata"] = point_metadata
    config["optimizer_strategy"] = strategy
    return {"config": config, "points": points, "stop_reason": "" if points else "no new sweep points"}


def composite_objective(row: pd.Series | dict) -> float:
    hard_failures = _as_float(row.get("hard_constraint_failure_count"))
    if hard_failures is None:
        hard_failures = _failure_count(row.get("failure_reasons"))
    score = _as_float(row.get("overall_score")) or 0.0
    not_evaluable = _as_float(row.get("not_evaluable_metric_count")) or 0.0
    profile_score = _as_float(row.get("profile_score")) or 0.0
    analysis_bonus = max(
        [
            _as_float(row.get("dc_gain_db")) or 0.0,
            min((_as_float(row.get("frequency_hz")) or 0.0) / 1.0e9, 100.0),
            _as_float(row.get("switching_threshold_v")) or 0.0,
        ]
    )
    return -10000.0 * hard_failures + 100.0 * score - 100.0 * not_evaluable + profile_score + analysis_bonus


def encode_parameter_points(points: list[dict[str, object]], parameters: dict[str, Any]) -> np.ndarray:
    columns: list[list[float]] = []
    for point in points:
        row: list[float] = []
        for name, spec in parameters.items():
            values = _values(spec)
            lookup = {str(value): index for index, value in enumerate(values)}
            row.append(float(lookup.get(str(point.get(name)), 0)))
        columns.append(row)
    return np.asarray(columns, dtype=float)


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
    strategy: str = "adaptive",
) -> list[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    base_config = yaml.safe_load(sweep_path.read_text(encoding="utf-8")) or {}
    history_rows: list[dict] = []
    round_rows: list[dict] = []
    current_config = {**base_config, "optimizer_strategy": strategy}
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
            history_rows.append(enrich_history_row(
                {
                    "round_index": round_index,
                    **_metadata_for_summary(current_config, row),
                    **row,
                    "run_dir": str(absolute_run_dir),
                }
            ))

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
        ) if strategy == "adaptive" else build_strategy_sweep_config(
            base_config=base_config,
            history=history,
            best_run_dir=best_run_dir,
            max_runs=max_runs_per_round,
            seed=seed + round_index,
            exploration_ratio=exploration_ratio,
            strategy=strategy,
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
    leaderboard = stable_leaderboard(pd.DataFrame(history_rows))
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


def _model_ranked_points(
    parameters: dict[str, Any],
    history: pd.DataFrame,
    grid: list[dict[str, object]],
    *,
    strategy: str,
    seed: int,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    train = _training_history(history, parameters)
    if not grid:
        return []
    if len(train) < 3:
        return []
    y = np.asarray([composite_objective(row) for _, row in train.iterrows()], dtype=float)
    if len(set(np.round(y, 12))) <= 1:
        return []
    train_points = [{name: row.get(name) for name in parameters} for _, row in train.iterrows()]
    x_train = encode_parameter_points(train_points, parameters)
    x_grid = encode_parameter_points(grid, parameters)
    if strategy == "bayesian":
        kernel = Matern(nu=2.5) + WhiteKernel(noise_level=1e-6)
        model = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=seed)
        model.fit(x_train, y)
        mean, std = model.predict(x_grid, return_std=True)
        best = float(np.max(y))
        improvement = mean - best
        safe_std = np.where(std <= 1e-12, 1e-12, std)
        z = improvement / safe_std
        acquisition = improvement * norm.cdf(z) + safe_std * norm.pdf(z)
        source = "bayesian_acquisition"
        status = "gaussian_process_ei"
    else:
        model = RandomForestRegressor(n_estimators=100, random_state=seed, min_samples_leaf=1)
        model.fit(x_train, y)
        predictions = np.asarray([estimator.predict(x_grid) for estimator in model.estimators_])
        mean = predictions.mean(axis=0)
        acquisition = mean + 0.1 * predictions.std(axis=0)
        source = "surrogate_model"
        status = "random_forest_ucb"
    order = np.argsort(-acquisition)
    rows = []
    for index in order:
        rows.append(
            (
                grid[int(index)],
                _source_metadata(
                    source,
                    model_status=status,
                    objective_score=float(acquisition[int(index)]),
                    model_prediction=float(mean[int(index)]),
                ),
            )
        )
    return rows


def _genetic_points(
    parameters: dict[str, Any],
    history: pd.DataFrame,
    *,
    max_runs: int,
    seed: int,
) -> list[tuple[dict[str, object], dict[str, object]]]:
    rng = random.Random(seed)
    train = _training_history(history, parameters)
    if train.empty:
        parents = _all_points(parameters)[:2]
    else:
        ranked = train.copy()
        ranked["_objective"] = [composite_objective(row) for _, row in ranked.iterrows()]
        ranked = ranked.sort_values("_objective", ascending=False)
        parents = [{name: row.get(name) for name in parameters} for _, row in ranked.head(max(2, min(6, len(ranked)))).iterrows()]
    children: list[tuple[dict[str, object], dict[str, object]]] = []
    attempts = max_runs * 20
    for _ in range(attempts):
        if len(children) >= max_runs:
            break
        if len(parents) >= 2:
            left, right = rng.sample(parents, 2)
        else:
            left = right = parents[0] if parents else {name: _values(spec)[0] for name, spec in parameters.items()}
        child = {}
        for name, spec in parameters.items():
            values = _values(spec)
            inherited = left.get(name) if rng.random() < 0.5 else right.get(name)
            child[name] = rng.choice(values) if rng.random() < 0.35 else inherited
            if child[name] not in values:
                child[name] = rng.choice(values)
        children.append(
            (
                child,
                _source_metadata(
                    "genetic_search",
                    model_status="crossover_mutation",
                    objective_score="",
                    source_candidate_parameters_json=_json_text(child),
                ),
            )
        )
    return children


def _diverse_points(
    parameters: dict[str, Any],
    history: pd.DataFrame,
    grid: list[dict[str, object]],
    *,
    seed: int,
) -> list[dict[str, object]]:
    if not grid:
        return []
    rng = random.Random(seed)
    selected: list[dict[str, object]] = []
    remaining = list(grid)
    history_points = [{name: row.get(name) for name in parameters} for _, row in history.iterrows()] if not history.empty else []
    while remaining:
        encoded_existing = encode_parameter_points([*history_points, *selected], parameters) if history_points or selected else None
        best_index = 0
        best_distance = float("-inf")
        rng.shuffle(remaining)
        for index, point in enumerate(remaining):
            if encoded_existing is None or encoded_existing.size == 0:
                distance = 0.0
            else:
                encoded = encode_parameter_points([point], parameters)
                distance = float(np.min(np.linalg.norm(encoded_existing - encoded, axis=1)))
            if distance > best_distance:
                best_distance = distance
                best_index = index
        selected.append(remaining.pop(best_index))
    return selected


def _training_history(history: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    train = history.copy()
    for name in parameters:
        if name not in train:
            return train.iloc[0:0].copy()
    if "status" in train:
        train = train[train["status"].eq("evaluated")]
    return train.dropna(subset=list(parameters), how="any")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _profile_metric_scores(value: object) -> list[float]:
    scores: list[float] = []
    if not isinstance(value, dict):
        return scores
    for item in value.values():
        if isinstance(item, dict):
            score = _as_float(item.get("score"))
        else:
            score = _as_float(item)
        if score is not None:
            scores.append(score)
    return scores


def stable_leaderboard(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    ranked = history.copy()
    if "rank_status" not in ranked:
        ranked["rank_status"] = [_rank_status(row) for _, row in ranked.iterrows()]
    scores = pd.to_numeric(ranked.get("overall_score"), errors="coerce")
    status_order = {"evaluated": 0, "not_evaluable": 1, "skipped": 2, "failed": 3}
    ranked["_score"] = scores.fillna(float("-inf"))
    ranked["_status_order"] = ranked["rank_status"].map(status_order).fillna(9)
    round_values = ranked["round_index"] if "round_index" in ranked else pd.Series([0] * len(ranked), index=ranked.index)
    ranked["_round"] = pd.to_numeric(round_values, errors="coerce").fillna(0)
    ranked["_run"] = ranked.get("run_dir", "").astype(str)
    ranked = ranked.sort_values(["_status_order", "_score", "_round", "_run"], ascending=[True, False, True, True])
    return ranked.drop(columns=["_score", "_status_order", "_round", "_run"])


def enrich_history_row(row: dict) -> dict:
    enriched = dict(row)
    run_dir = Path(str(enriched.get("run_dir", "")))
    score = _read_json(run_dir / "score_summary.json")
    analysis = _read_json(run_dir / "analysis_metrics.json")
    if score:
        failures = score.get("hard_constraint_failures", [])
        enriched["hard_constraint_failure_count"] = int(_failure_count(failures))
        if "hard_constraint_passed" in score:
            enriched["hard_constraint_passed"] = score.get("hard_constraint_passed")
        if "profile_score" in score:
            enriched["profile_score"] = score.get("profile_score")
        if "topology_profile" in score:
            enriched["topology_profile"] = score.get("topology_profile")
    else:
        enriched.setdefault("hard_constraint_failure_count", int(_failure_count(enriched.get("failure_reasons"))))
    if analysis:
        not_evaluable = analysis.get("not_evaluable_metrics", {})
        enriched["not_evaluable_metric_count"] = len(not_evaluable) if isinstance(not_evaluable, dict) else 0
        scores = _profile_metric_scores(analysis.get("profile_metric_scores", {}))
        if scores:
            enriched["profile_metric_score_mean"] = float(np.mean(scores))
    enriched.setdefault("not_evaluable_metric_count", 0)
    return enriched


def _candidate_points(best_run_dir: Path | None, baseline: dict[str, object]) -> list[tuple[dict[str, object], dict[str, object]]]:
    if best_run_dir is None:
        return []
    path = best_run_dir / "next_candidates.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    if "search_score" in frame:
        frame["_score"] = pd.to_numeric(frame["search_score"], errors="coerce").fillna(0)
        frame = frame.sort_values("_score", ascending=False)
    points: list[tuple[dict[str, object], dict[str, object]]] = []
    for _, row in frame.iterrows():
        changes = _candidate_change_dict(row)
        if not changes:
            continue
        metadata = _source_metadata(
            "next_candidates",
            source_run_dir=str(best_run_dir),
            source_candidate_id=row.get("candidate_id", ""),
            source_candidate_trigger_metric=row.get("trigger_metric", ""),
            source_candidate_kind=row.get("candidate_kind", ""),
            source_candidate_score=row.get("search_score", ""),
            source_candidate_parameters_json=_json_text(row.get("parameters_json") or changes),
            source_candidate_rationale=row.get("rationale", ""),
        )
        points.append(({**baseline, **changes}, metadata))
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
    point_metadata: list[dict[str, object]],
    point: dict[str, object],
    metadata: dict[str, object],
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
    point_metadata.append(metadata)


def _metadata_for_summary(config: dict, row: dict) -> dict[str, object]:
    metadata_rows = config.get("point_metadata")
    if isinstance(metadata_rows, list):
        index = _as_int(row.get("sweep_point_index"))
        if index is not None and 1 <= index <= len(metadata_rows) and isinstance(metadata_rows[index - 1], dict):
            metadata = dict(metadata_rows[index - 1])
        else:
            metadata = _source_metadata("initial_grid")
    else:
        metadata = _source_metadata(
            "initial_grid",
            optimizer_strategy=str(config.get("optimizer_strategy", "")),
            model_status="initial_grid",
        )
    metadata["rank_status"] = _rank_status(row)
    return metadata


def _source_metadata(candidate_source: str, **values) -> dict[str, object]:
    metadata = {
        "candidate_source": candidate_source,
        "source_run_dir": "",
        "source_candidate_id": "",
        "source_candidate_trigger_metric": "",
        "source_candidate_kind": "",
        "source_candidate_score": "",
        "source_candidate_parameters_json": "",
        "source_candidate_rationale": "",
        "optimizer_strategy": "",
        "objective_score": "",
        "model_status": "",
        "model_prediction": "",
    }
    metadata.update({key: "" if value is None or (isinstance(value, float) and pd.isna(value)) else value for key, value in values.items()})
    return metadata


def _rank_status(row: pd.Series | dict) -> str:
    status = str(row.get("status", "") or "").lower()
    score = _as_float(row.get("overall_score"))
    if status == "evaluated" and score is not None:
        return "evaluated"
    if status == "evaluated":
        return "not_evaluable"
    if status == "skipped":
        return "skipped"
    if status == "failed":
        return "failed"
    return status or "unknown"


def _all_points(parameters: dict[str, Any]) -> list[dict[str, object]]:
    if not parameters:
        return []
    names = list(parameters)
    points = [{}]
    for name in names:
        values = _values(parameters[name])
        points = [{**point, name: value} for point in points for value in values]
    return points


def _point_key(point: dict[str, object], parameters: dict[str, Any]) -> tuple:
    return tuple(point.get(name) for name in parameters)


def _fallback_reason(history: pd.DataFrame) -> str:
    train = history.copy() if not history.empty else history
    if train.empty:
        return "fallback_insufficient_history"
    if "status" in train:
        train = train[train["status"].eq("evaluated")]
    if len(train) < 3:
        return "fallback_insufficient_history"
    values = [composite_objective(row) for _, row in train.iterrows()]
    if len(set(np.round(values, 12))) <= 1:
        return "fallback_zero_variance"
    return "fallback_fill"


def _failure_count(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, list):
        return float(len([item for item in value if item]))
    text = str(value)
    if not text.strip():
        return 0.0
    return float(len([item for item in text.split(";") if item.strip()]))


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


def _as_int(value) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_text(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
