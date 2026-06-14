from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import math
import random
from typing import Any

import pandas as pd

from goa_eval.io_utils import as_float as _as_float, json_number as _json_number, write_json
from goa_eval.optimizer import load_param_space
from goa_eval.param_space import parse_engineering_value
from goa_eval.pareto import DEFAULT_OBJECTIVES, pareto_rank, select_knee_points
from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


PREDICTED_METRICS = [
    "overall_score",
    "Max_overlap_ratio",
    "Max_ripple",
    "Max_voltage_loss",
    "Delay_std",
]

OUTPUT_COLUMNS = [
    "schema_version",
    "result_version",
    "candidate_id",
    "candidate_source",
    "parameters_json",
    "changed_parameters",
    "predicted_overall_score",
    "predicted_Max_overlap_ratio",
    "predicted_Max_ripple",
    "predicted_Max_voltage_loss",
    "predicted_Delay_std",
    "predicted_hard_constraint_passed",
    "surrogate_rank",
    "pareto_rank",
    "pareto_is_front",
    "dominance_count",
    "candidate_style",
    "repair_operator",
    "trigger_metric",
    "trigger_value",
    "repair_rationale",
    "mutation_strength",
    "is_conservative",
    "model_status",
    "recommendation_rationale",
    "predicted_improvement",
    "predicted_score_gain",
    "candidate_quality_proxy",
    "data_source",
    "engineering_validity",
    "evidence_level",
    "simulation_backend",
    "mock_used",
]


def run_hybrid_goa_optimizer(
    *,
    history_path: Path | None,
    leaderboard_path: Path | None,
    param_space_path: Path | None,
    output_root: Path,
    max_candidates: int = 30,
    seed: int = 42,
    hybrid_candidate_mix: dict[str, float] | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    history = _load_history(history_path)
    leaderboard = _load_csv(leaderboard_path)
    samples = _merge_samples(history, leaderboard)
    param_space = load_param_space(param_space_path) if param_space_path else _infer_param_space(samples)
    param_names = list(param_space.keys())
    model_bundle = _fit_surrogate(samples, param_names)
    counts = _candidate_counts(max_candidates, hybrid_candidate_mix or {"surrogate": 0.5, "repair": 0.3, "exploration": 0.2})
    rng = random.Random(seed)

    candidates: list[dict[str, Any]] = []
    candidates.extend(_generate_surrogate_candidates(samples, param_space, model_bundle, counts["surrogate"], rng))
    candidates.extend(generate_repair_candidates(samples, param_space, max_candidates=counts["repair"], seed=seed + 17))
    candidates.extend(_generate_exploration_candidates(samples, param_space, counts["exploration"], rng))
    candidates = _ensure_source_coverage(candidates, samples, param_space, model_bundle, rng, max_candidates)
    candidates = _dedupe_candidates(candidates)[:max_candidates]
    candidates = _score_candidates(candidates, samples, model_bundle, param_names)
    candidate_frame = pd.DataFrame(candidates)
    candidate_frame = pareto_rank(candidate_frame, _candidate_objectives())
    candidate_frame = _final_sort(candidate_frame).head(max_candidates).copy()
    candidate_frame["candidate_id"] = [f"hybrid_{index:03d}" for index in range(1, len(candidate_frame) + 1)]
    candidate_frame = _complete_output_columns(candidate_frame)

    candidate_frame.to_csv(output_root / "hybrid_candidates.csv", index=False, encoding="utf-8-sig")
    (output_root / "hybrid_candidates.md").write_text(_candidate_markdown(candidate_frame), encoding="utf-8")
    front = candidate_frame[candidate_frame["pareto_is_front"].astype(str).str.lower() == "true"].copy()
    front.to_csv(output_root / "pareto_front.csv", index=False, encoding="utf-8-sig")
    pareto_summary = _pareto_summary(candidate_frame, param_names)
    write_json(output_root / "pareto_summary.json", pareto_summary)
    summary = _optimizer_summary(candidate_frame, samples, model_bundle, param_names, history_path, leaderboard_path, param_space_path, pareto_summary)
    write_json(output_root / "hybrid_optimizer_summary.json", summary)
    (output_root / "hybrid_optimizer_report.md").write_text(_optimizer_report(summary, candidate_frame), encoding="utf-8")
    return summary


def generate_repair_candidates(
    history: pd.DataFrame,
    param_space: dict[str, Any],
    *,
    max_candidates: int = 10,
    seed: int = 42,
) -> list[dict[str, Any]]:
    if history.empty or not param_space or max_candidates <= 0:
        return []
    rng = random.Random(seed)
    rows = _failure_rows(history)
    candidates: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        trigger = _dominant_failure(row)
        if not trigger:
            continue
        metric, operator, rationale, categories, conservative = trigger
        base_params = _extract_parameters(row, param_space.keys())
        targets = _parameters_for_categories(param_space, categories)
        if not targets:
            targets = list(param_space.keys())
        mutation_strength = 0.08 if conservative else 0.18
        for target in targets[:2]:
            repaired = dict(base_params)
            repaired[target] = _mutated_value(target, base_params.get(target), param_space[target], rng, conservative=conservative)
            changed = sorted(key for key in repaired if base_params.get(key) != repaired.get(key))
            if not changed:
                continue
            candidates.append(
                _candidate(
                    source="repair",
                    parameters=repaired,
                    changed_parameters=changed,
                    rationale=rationale,
                    repair_operator=operator,
                    trigger_metric=metric,
                    trigger_value=row.get(metric, ""),
                    repair_rationale=rationale,
                    mutation_strength=mutation_strength,
                    is_conservative=conservative,
                    model_status="repair_rule_based",
                )
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates[:max_candidates]


def _fit_surrogate(samples: pd.DataFrame, param_names: list[str]) -> dict[str, Any]:
    usable = _feature_frame(samples, param_names)
    status = "fallback_insufficient_data"
    models: dict[str, Any] = {}
    metric_defaults = _metric_defaults(samples)
    if len(usable) < 3 or not param_names:
        return {"status": status, "models": models, "defaults": metric_defaults, "feature_columns": param_names}
    try:
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestRegressor
    except Exception:
        return {"status": "fallback_sklearn_unavailable", "models": models, "defaults": metric_defaults, "feature_columns": param_names}

    x = usable[param_names]
    trained = 0
    for metric in PREDICTED_METRICS:
        if metric not in samples.columns:
            continue
        y = pd.to_numeric(samples.loc[usable.index, metric], errors="coerce")
        mask = y.notna()
        if mask.sum() < 3:
            continue
        model = RandomForestRegressor(n_estimators=64, random_state=17, min_samples_leaf=1)
        model.fit(x.loc[mask], y.loc[mask])
        models[metric] = model
        trained += 1
    labels = samples.loc[usable.index].apply(_row_hard_passed, axis=1)
    if labels.notna().sum() >= 3 and labels.nunique(dropna=True) > 1:
        classifier = ExtraTreesClassifier(n_estimators=64, random_state=17)
        classifier.fit(x.loc[labels.notna()], labels.loc[labels.notna()].astype(bool))
        models["hard_constraint_passed"] = classifier
        trained += 1
    if trained:
        status = "trained_sklearn_random_forest"
    return {"status": status, "models": models, "defaults": metric_defaults, "feature_columns": param_names}


def _generate_surrogate_candidates(
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    model_bundle: dict[str, Any],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    pool = [_sample_parameters(param_space, rng) for _ in range(max(count * 8, count))]
    scored = []
    for params in pool:
        predictions = _predict_metrics(params, model_bundle)
        scored.append((predictions.get("overall_score", 0.0), params, predictions))
    scored.sort(key=lambda item: (-float(item[0] or 0.0), json.dumps(item[1], sort_keys=True, ensure_ascii=False)))
    candidates = []
    baseline = _best_parameters(samples, param_space)
    for rank, (_, params, predictions) in enumerate(scored[:count], start=1):
        changed = _changed_parameters(baseline, params)
        candidates.append(
            _candidate(
                source="surrogate",
                parameters=params,
                changed_parameters=changed or sorted(params),
                rationale="surrogate-predicted candidate balancing GOA waveform quality and hard constraints",
                model_status=model_bundle["status"],
                surrogate_rank=rank,
                predictions=predictions,
                mutation_strength=_mutation_strength(baseline, params),
            )
        )
    return candidates


def _generate_exploration_candidates(
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    baseline = _best_parameters(samples, param_space)
    candidates = []
    for _ in range(count):
        params = _sample_parameters(param_space, rng)
        changed = _changed_parameters(baseline, params)
        candidates.append(
            _candidate(
                source="exploration",
                parameters=params,
                changed_parameters=changed or sorted(params),
                rationale="diversity candidate for GOA parameter-space coverage before the next simulation round",
                model_status="diversity_sampling",
                mutation_strength=max(0.2, _mutation_strength(baseline, params)),
            )
        )
    return candidates


def _score_candidates(
    candidates: list[dict[str, Any]],
    samples: pd.DataFrame,
    model_bundle: dict[str, Any],
    param_names: list[str],
) -> list[dict[str, Any]]:
    best_score = _best_score(samples)
    for candidate in candidates:
        predictions = candidate.get("_predictions") or _predict_metrics(candidate["_parameters"], model_bundle)
        for metric in PREDICTED_METRICS:
            candidate[f"predicted_{metric}"] = predictions.get(metric)
        hard_prediction = predictions.get("hard_constraint_passed")
        candidate["predicted_hard_constraint_passed"] = bool(hard_prediction) if hard_prediction is not None else _default_hard_pass(samples)
        score = _as_float(candidate.get("predicted_overall_score")) or 0.0
        candidate["predicted_score_gain"] = score - best_score if best_score is not None else None
        candidate["predicted_improvement"] = candidate["predicted_score_gain"]
        candidate["candidate_quality_proxy"] = _quality_proxy(candidate)
        candidate["parameters_json"] = json.dumps(candidate.pop("_parameters"), ensure_ascii=False, sort_keys=True)
        candidate.pop("_predictions", None)
    return candidates


def _predict_metrics(params: dict[str, Any], model_bundle: dict[str, Any]) -> dict[str, Any]:
    models = model_bundle.get("models", {})
    defaults = dict(model_bundle.get("defaults", {}))
    features = model_bundle.get("feature_columns", [])
    feature_row = {}
    for name in features:
        value = _numeric(params.get(name))
        feature_row[name] = value if value is not None else 0.0
    x = pd.DataFrame([feature_row])
    predictions = dict(defaults)
    for metric, model in models.items():
        try:
            if metric == "hard_constraint_passed":
                if hasattr(model, "predict_proba"):
                    probability = model.predict_proba(x)[0][-1]
                    predictions[metric] = bool(probability >= 0.5)
                else:
                    predictions[metric] = bool(model.predict(x)[0])
            else:
                predictions[metric] = float(model.predict(x)[0])
        except Exception:
            continue
    return predictions


def _candidate(
    *,
    source: str,
    parameters: dict[str, Any],
    changed_parameters: list[str],
    rationale: str,
    model_status: str,
    predictions: dict[str, Any] | None = None,
    surrogate_rank: int | str = "",
    repair_operator: str = "",
    trigger_metric: str = "",
    trigger_value: Any = "",
    repair_rationale: str = "",
    mutation_strength: float = 0.0,
    is_conservative: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "candidate_source": source,
        "_parameters": parameters,
        "_predictions": predictions or {},
        "changed_parameters": ";".join(changed_parameters),
        "surrogate_rank": surrogate_rank,
        "repair_operator": repair_operator,
        "trigger_metric": trigger_metric,
        "trigger_value": trigger_value,
        "repair_rationale": repair_rationale,
        "mutation_strength": mutation_strength,
        "is_conservative": is_conservative,
        "model_status": model_status,
        "recommendation_rationale": rationale,
        "data_source": "benchmark-derived",
        "engineering_validity": "simulation_only",
        "evidence_level": "csv-derived",
        "simulation_backend": "no_real_ngspice_required",
        "mock_used": False,
    }


def _load_history(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        for key in ["history", "rows", "samples"]:
            if isinstance(payload.get(key), list):
                return pd.DataFrame(payload[key])
        return pd.DataFrame([payload])
    return pd.DataFrame()


def _load_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _merge_samples(history: pd.DataFrame, leaderboard: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in [history, leaderboard] if not frame.empty]
    if not frames:
        return pd.DataFrame()
    samples = pd.concat(frames, ignore_index=True, sort=False)
    if "parameters_json" not in samples.columns and "source_candidate_parameters_json" in samples.columns:
        samples["parameters_json"] = samples["source_candidate_parameters_json"]
    return samples


def _infer_param_space(samples: pd.DataFrame) -> dict[str, Any]:
    excluded = set(PREDICTED_METRICS) | {
        "candidate_id",
        "run_id",
        "status",
        "rank_status",
        "target_passed",
        "hard_constraint_passed",
        "parameters_json",
        "source_candidate_parameters_json",
        "data_source",
        "engineering_validity",
    }
    space: dict[str, Any] = {}
    for column in samples.columns:
        if column in excluded or column.startswith("predicted_"):
            continue
        values = [value for value in samples[column].dropna().unique().tolist() if str(value) != ""]
        if values and any(_numeric(value) is not None for value in values):
            space[column] = {"values": values}
    for _, row in samples.iterrows():
        for key, value in _json_parameters(row.get("parameters_json")).items():
            space.setdefault(key, {"values": []})
            if value not in space[key]["values"]:
                space[key]["values"].append(value)
    return space


def _feature_frame(samples: pd.DataFrame, param_names: list[str]) -> pd.DataFrame:
    rows = []
    indexes = []
    for index, row in samples.iterrows():
        params = _extract_parameters(row, param_names)
        if not params:
            continue
        rows.append({name: _numeric(params.get(name)) for name in param_names})
        indexes.append(index)
    return pd.DataFrame(rows, index=indexes).fillna(0.0)


def _metric_defaults(samples: pd.DataFrame) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for metric in PREDICTED_METRICS:
        if metric in samples.columns:
            values = pd.to_numeric(samples[metric], errors="coerce").dropna()
            defaults[metric] = float(values.median()) if not values.empty else _fallback_metric(metric)
        else:
            defaults[metric] = _fallback_metric(metric)
    defaults["hard_constraint_passed"] = _default_hard_pass(samples)
    return defaults


def _fallback_metric(metric: str) -> float:
    return 50.0 if metric == "overall_score" else 0.0


def _extract_parameters(row: pd.Series, param_names: Any) -> dict[str, Any]:
    params = _json_parameters(row.get("parameters_json"))
    if not params:
        params = _json_parameters(row.get("source_candidate_parameters_json"))
    for name in param_names:
        if name in row and not pd.isna(row.get(name)):
            params.setdefault(name, row.get(name))
    return {str(name): value for name, value in params.items() if str(name) in set(str(param) for param in param_names)}


def _json_parameters(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _failure_rows(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history
    scored = history.copy()
    scored["_failure_score"] = scored.apply(_failure_score, axis=1)
    return scored.sort_values(["_failure_score"], ascending=[False], kind="mergesort")


def _failure_score(row: pd.Series) -> float:
    total = 0.0
    for metric in ["Max_overlap_ratio", "Max_ripple", "Max_voltage_loss", "Delay_std"]:
        total += max(0.0, _as_float(row.get(metric)) or 0.0)
    total += 2.0 * max(0.0, _as_float(row.get("not_evaluable_metric_count")) or 0.0)
    if str(row.get("rank_status", "")).lower() == "not_evaluable":
        total += 10.0
    if _row_hard_passed(row) is False:
        total += 2.0
    return total


def _dominant_failure(row: pd.Series) -> tuple[str, str, str, list[str], bool] | None:
    if str(row.get("rank_status", "")).lower() == "not_evaluable" or (_as_float(row.get("not_evaluable_metric_count")) or 0) > 0:
        return (
            "not_evaluable_metric_count",
            "recover_evaluability_conservative_repair",
            "recover evaluability before aggressive optimization",
            ["generic"],
            True,
        )
    metrics = {
        "Max_overlap_ratio": (
            _as_float(row.get("Max_overlap_ratio")) or 0.0,
            "overlap_timing_repair",
            "reduce overlap / improve stage separation",
            ["timing", "drive", "load"],
        ),
        "Max_ripple": (
            _as_float(row.get("Max_ripple")) or 0.0,
            "ripple_stability_repair",
            "reduce ripple / improve waveform stability",
            ["load", "cap", "drive"],
        ),
        "Max_voltage_loss": (
            _as_float(row.get("Max_voltage_loss")) or 0.0,
            "voltage_loss_drive_margin_repair",
            "reduce voltage loss / improve drive margin",
            ["drive", "load", "resistance"],
        ),
        "Delay_std": (
            _as_float(row.get("Delay_std")) or 0.0,
            "delay_dispersion_repair",
            "reduce delay dispersion",
            ["timing", "drive"],
        ),
    }
    metric, (value, operator, rationale, categories) = max(metrics.items(), key=lambda item: item[1][0])
    if value <= 0:
        return None
    return metric, operator, rationale, categories, False


def _parameters_for_categories(param_space: dict[str, Any], categories: list[str]) -> list[str]:
    matches = []
    for name in param_space:
        param_categories = set(_parameter_categories(name))
        if "generic" in categories or param_categories.intersection(categories):
            matches.append(name)
    return matches


def _parameter_categories(name: str) -> list[str]:
    text = name.lower()
    categories = []
    if any(token in text for token in ["delay", "time", "clk", "period", "phase"]):
        categories.append("timing")
    if any(token in text for token in ["drive", "strength", "width", "w_", "wn", "wp"]):
        categories.append("drive")
    if any(token in text for token in ["load", "cap", "c_"]):
        categories.extend(["load", "cap"])
    if any(token in text for token in ["res", "r_"]):
        categories.append("resistance")
    return categories or ["generic"]


def _mutated_value(name: str, current: Any, entry: Any, rng: random.Random, *, conservative: bool) -> Any:
    values = _values(entry)
    if not values:
        return current
    if current in values:
        index = values.index(current)
    else:
        numeric_current = _numeric(current)
        numeric_values = [_numeric(value) for value in values]
        if numeric_current is not None and any(value is not None for value in numeric_values):
            index = min(range(len(values)), key=lambda idx: abs((numeric_values[idx] or 0.0) - numeric_current))
        else:
            index = len(values) // 2
    step = 1 if conservative else rng.choice([-1, 1])
    if any(token in name.lower() for token in ["res", "r_"]) and not conservative:
        step = -1
    next_index = max(0, min(len(values) - 1, index + step))
    if next_index == index and len(values) > 1:
        next_index = index - 1 if index > 0 else index + 1
    return values[next_index]


def _sample_parameters(param_space: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    return {name: rng.choice(_values(entry) or [""]) for name, entry in param_space.items()}


def _values(entry: Any) -> list[Any]:
    if isinstance(entry, dict):
        values = entry.get("values", [])
        return list(values) if isinstance(values, list) else [values]
    return list(entry) if isinstance(entry, list) else [entry]


def _best_parameters(samples: pd.DataFrame, param_space: dict[str, Any]) -> dict[str, Any]:
    if samples.empty:
        return {name: (_values(entry) or [""])[0] for name, entry in param_space.items()}
    ranked = samples.copy()
    ranked["_score"] = pd.to_numeric(ranked.get("overall_score"), errors="coerce").fillna(float("-inf"))
    ranked = ranked.sort_values("_score", ascending=False, kind="mergesort")
    params = _extract_parameters(ranked.iloc[0], param_space.keys()) if not ranked.empty else {}
    for name, entry in param_space.items():
        params.setdefault(name, (_values(entry) or [""])[0])
    return params


def _changed_parameters(base: dict[str, Any], params: dict[str, Any]) -> list[str]:
    return sorted(name for name, value in params.items() if str(base.get(name)) != str(value))


def _mutation_strength(base: dict[str, Any], params: dict[str, Any]) -> float:
    if not params:
        return 0.0
    return len(_changed_parameters(base, params)) / len(params)


def _candidate_counts(max_candidates: int, mix: dict[str, float]) -> dict[str, int]:
    max_candidates = max(0, int(max_candidates))
    if max_candidates == 0:
        return {"surrogate": 0, "repair": 0, "exploration": 0}
    counts = {key: int(math.floor(max_candidates * float(mix.get(key, 0.0)))) for key in ["surrogate", "repair", "exploration"]}
    for key in ["surrogate", "repair", "exploration"]:
        if max_candidates >= 3 and counts[key] == 0:
            counts[key] = 1
    while sum(counts.values()) < max_candidates:
        counts["surrogate"] += 1
    while sum(counts.values()) > max_candidates:
        for key in ["exploration", "repair", "surrogate"]:
            if counts[key] > 1:
                counts[key] -= 1
                break
    return counts


def _ensure_source_coverage(
    candidates: list[dict[str, Any]],
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    model_bundle: dict[str, Any],
    rng: random.Random,
    max_candidates: int,
) -> list[dict[str, Any]]:
    if max_candidates < 3:
        return candidates
    sources = {candidate["candidate_source"] for candidate in candidates}
    if "surrogate" not in sources:
        candidates.extend(_generate_surrogate_candidates(samples, param_space, model_bundle, 1, rng))
    if "repair" not in sources:
        base = _best_parameters(samples, param_space)
        name = next(iter(param_space), "")
        if name:
            params = dict(base)
            params[name] = _mutated_value(name, params.get(name), param_space[name], rng, conservative=True)
            candidates.append(
                _candidate(
                    source="repair",
                    parameters=params,
                    changed_parameters=_changed_parameters(base, params) or [name],
                    rationale="recover evaluability before aggressive optimization",
                    repair_operator="recover_evaluability_conservative_repair",
                    trigger_metric="not_evaluable_metric_count",
                    repair_rationale="recover evaluability before aggressive optimization",
                    model_status="repair_rule_based",
                    mutation_strength=0.08,
                    is_conservative=True,
                )
            )
    if "exploration" not in sources:
        candidates.extend(_generate_exploration_candidates(samples, param_space, 1, rng))
    return candidates


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for candidate in candidates:
        key = (candidate.get("candidate_source"), json.dumps(candidate.get("_parameters", {}), ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _candidate_objectives() -> list[dict[str, str]]:
    objectives = []
    for objective in DEFAULT_OBJECTIVES:
        name = objective["name"]
        if name in {"overall_score", "Max_overlap_ratio", "Max_ripple", "Max_voltage_loss", "Delay_std", "hard_constraint_passed"}:
            name = f"predicted_{name}"
        objectives.append({"name": name, "direction": objective["direction"]})
    return objectives


def _final_sort(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sortable = frame.copy()
    sortable["_hard"] = sortable["predicted_hard_constraint_passed"].astype(bool)
    sortable["_score"] = pd.to_numeric(sortable["predicted_overall_score"], errors="coerce").fillna(float("-inf"))
    sortable["_diversity"] = sortable["changed_parameters"].astype(str).str.count(";").fillna(0)
    return sortable.sort_values(
        ["_hard", "pareto_rank", "_score", "_diversity", "candidate_source"],
        ascending=[False, True, False, False, True],
        kind="mergesort",
    ).drop(columns=["_hard", "_score", "_diversity"])


def _complete_output_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[OUTPUT_COLUMNS]


def _pareto_summary(frame: pd.DataFrame, param_names: list[str]) -> dict[str, Any]:
    source_counts = Counter(frame["candidate_source"]) if "candidate_source" in frame.columns else Counter()
    count = len(frame)
    front = frame[frame["pareto_is_front"].astype(str).str.lower() == "true"] if "pareto_is_front" in frame.columns else pd.DataFrame()
    return {
        "candidate_count": count,
        "pareto_front_count": len(front),
        "objective_config": _candidate_objectives(),
        "best_balanced_candidate_id": _best_style(frame, "balanced"),
        "best_conservative_candidate_id": _best_style(frame, "conservative") or _best_style(frame, "repair_first"),
        "best_aggressive_candidate_id": _best_style(frame, "aggressive"),
        "hard_constraint_pass_rate_predicted": float(frame["predicted_hard_constraint_passed"].astype(bool).mean()) if count else 0.0,
        "not_evaluable_rate_predicted": float((~frame["predicted_hard_constraint_passed"].astype(bool)).mean()) if count else 0.0,
        "pareto_front_hit_rate": len(front) / count if count else 0.0,
        "avg_pareto_rank": _json_number(pd.to_numeric(frame.get("pareto_rank"), errors="coerce").mean()) if count else None,
        "best_predicted_score_mean": _json_number(pd.to_numeric(frame.get("predicted_overall_score"), errors="coerce").head(3).mean()) if count else None,
        "repair_candidate_ratio": source_counts.get("repair", 0) / count if count else 0.0,
        "surrogate_candidate_ratio": source_counts.get("surrogate", 0) / count if count else 0.0,
        "exploration_candidate_ratio": source_counts.get("exploration", 0) / count if count else 0.0,
        "candidate_diversity_score": _diversity_score(frame, param_names),
    }


def _optimizer_summary(
    frame: pd.DataFrame,
    samples: pd.DataFrame,
    model_bundle: dict[str, Any],
    param_names: list[str],
    history_path: Path | None,
    leaderboard_path: Path | None,
    param_space_path: Path | None,
    pareto_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "task_type": "goa_hybrid_optimizer",
        "boundary": {
            "mainline": "GOA",
            "engineering_validity": "simulation_only",
            "real_ngspice_required": False,
            "claim": "candidate recommendation only; next simulation is still required",
        },
        "input_data": {
            "history": str(history_path) if history_path else "",
            "leaderboard": str(leaderboard_path) if leaderboard_path else "",
            "param_space": str(param_space_path) if param_space_path else "",
            "row_count": len(samples),
            "parameter_columns": param_names,
            "metric_columns": [metric for metric in PREDICTED_METRICS if metric in samples.columns],
        },
        "surrogate_model": {
            "model_status": model_bundle.get("status"),
            "training_sample_count": len(samples),
            "target_metrics": PREDICTED_METRICS,
        },
        "candidate_count": len(frame),
        "candidate_sources": dict(Counter(frame["candidate_source"])) if "candidate_source" in frame.columns else {},
        "pareto": pareto_summary,
        "data_source": "benchmark-derived",
        "engineering_validity": "simulation_only",
        "evidence_level": "csv-derived",
        "simulation_backend": "no_real_ngspice_required",
        "mock_used": False,
    }


def _optimizer_report(summary: dict[str, Any], frame: pd.DataFrame) -> str:
    lines = [
        "# Hybrid GOA Optimizer Report",
        "",
        "## 1. Task Boundary",
        "",
        "This run is a GOA simulation-only optimizer. It uses CSV/benchmark-derived results, has no real ngspice required boundary, and does not claim silicon or physical validation.",
        "",
        "## 2. Input Data",
        "",
        f"- History: `{summary['input_data']['history']}`",
        f"- Leaderboard: `{summary['input_data']['leaderboard']}`",
        f"- Param space: `{summary['input_data']['param_space']}`",
        f"- Rows: `{summary['input_data']['row_count']}`",
        f"- Parameter columns: `{', '.join(summary['input_data']['parameter_columns'])}`",
        f"- Metric columns: `{', '.join(summary['input_data']['metric_columns'])}`",
        "",
        "## 3. Surrogate Model",
        "",
        f"- Model status: `{summary['surrogate_model']['model_status']}`",
        f"- Training samples: `{summary['surrogate_model']['training_sample_count']}`",
        f"- Target metrics: `{', '.join(summary['surrogate_model']['target_metrics'])}`",
        "",
        "## 4. Failure-guided Repair Search",
        "",
    ]
    repair_ops = sorted({str(value) for value in frame.get("repair_operator", []) if str(value)})
    lines.append(f"- Repair operators: `{', '.join(repair_ops)}`" if repair_ops else "- Repair operators: none")
    lines.extend(
        [
            "",
            "## 5. Pareto Evaluation",
            "",
            f"- Pareto front count: `{summary['pareto']['pareto_front_count']}`",
            f"- Objective config: `{summary['pareto']['objective_config']}`",
            "",
            "## 6. Top Candidates",
            "",
            "| candidate_id | source | style | pareto_rank | predicted_score | changed_parameters | rationale |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for _, row in frame.head(10).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id", "")),
                    str(row.get("candidate_source", "")),
                    str(row.get("candidate_style", "")),
                    str(row.get("pareto_rank", "")),
                    str(row.get("predicted_overall_score", "")),
                    str(row.get("changed_parameters", "")),
                    str(row.get("recommendation_rationale", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 7. Engineering Interpretation",
            "",
            "Hard constraints and evaluability are interpreted before soft score. Candidates combine surrogate, repair, and exploration sources, but they remain prediction / candidate recommendation artifacts and still need the next simulation round.",
        ]
    )
    return "\n".join(lines) + "\n"


def _candidate_markdown(frame: pd.DataFrame) -> str:
    lines = [
        "# Hybrid GOA Candidates",
        "",
        "- data_source: `benchmark-derived`",
        "- engineering_validity: `simulation_only`",
        "- evidence_level: `csv-derived`",
        "- simulation_backend: `no_real_ngspice_required`",
        "",
    ]
    for _, row in frame.iterrows():
        lines.extend(
            [
                f"## {row['candidate_id']}",
                "",
                f"- source: `{row['candidate_source']}`",
                f"- style: `{row['candidate_style']}`",
                f"- pareto_rank: `{row['pareto_rank']}`",
                f"- predicted_overall_score: `{row['predicted_overall_score']}`",
                f"- changed_parameters: `{row['changed_parameters']}`",
                f"- rationale: {row['recommendation_rationale']}",
                "",
            ]
        )
    return "\n".join(lines)


def _best_style(frame: pd.DataFrame, style: str) -> str:
    if frame.empty or "candidate_style" not in frame.columns:
        return ""
    match = frame[frame["candidate_style"] == style]
    return str(match.iloc[0]["candidate_id"]) if not match.empty else ""


def _diversity_score(frame: pd.DataFrame, param_names: list[str]) -> float:
    if frame.empty or not param_names:
        return 0.0
    changed = set()
    for value in frame.get("changed_parameters", []):
        changed.update(item for item in str(value).split(";") if item)
    return len(changed.intersection(param_names)) / len(param_names)


def _quality_proxy(candidate: dict[str, Any]) -> float:
    score = _as_float(candidate.get("predicted_overall_score")) or 0.0
    hard = 10.0 if bool(candidate.get("predicted_hard_constraint_passed")) else -10.0
    penalties = sum(_as_float(candidate.get(f"predicted_{metric}")) or 0.0 for metric in ["Max_overlap_ratio", "Max_ripple", "Max_voltage_loss", "Delay_std"])
    return score + hard - penalties


def _best_score(samples: pd.DataFrame) -> float | None:
    if samples.empty or "overall_score" not in samples.columns:
        return None
    values = pd.to_numeric(samples["overall_score"], errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _row_hard_passed(row: pd.Series) -> bool | None:
    value = row.get("hard_constraint_passed")
    if value is True or str(value).strip().lower() == "true":
        return True
    if value is False or str(value).strip().lower() == "false":
        return False
    failures = _as_float(row.get("hard_constraint_failure_count"))
    if failures is not None:
        return failures <= 0
    return None


def _default_hard_pass(samples: pd.DataFrame) -> bool:
    if samples.empty:
        return False
    values = samples.apply(_row_hard_passed, axis=1).dropna()
    return bool(values.mean() >= 0.5) if len(values) else False


def _numeric(value: Any) -> float | None:
    parsed = parse_engineering_value(value)
    if parsed is not None:
        return parsed
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


best_goa_parameters = _best_parameters
best_goa_score = _best_score
build_goa_candidate = _candidate
changed_goa_parameters = _changed_parameters
complete_goa_output_columns = _complete_output_columns
dedupe_goa_candidates = _dedupe_candidates
ensure_goa_source_coverage = _ensure_source_coverage
fit_goa_surrogate = _fit_surrogate
generate_goa_exploration_candidates = _generate_exploration_candidates
generate_goa_surrogate_candidates = _generate_surrogate_candidates
goa_candidate_counts = _candidate_counts
goa_mutation_strength = _mutation_strength
load_goa_csv = _load_csv
load_goa_history = _load_history
merge_goa_samples = _merge_samples
predict_goa_metrics = _predict_metrics
sample_goa_parameters = _sample_parameters
score_goa_candidates = _score_candidates
