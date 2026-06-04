from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import math
import random
from typing import Any

import pandas as pd

from goa_eval.goa_hybrid_optimizer import (
    best_goa_parameters,
    best_goa_score,
    build_goa_candidate,
    changed_goa_parameters,
    complete_goa_output_columns,
    dedupe_goa_candidates,
    ensure_goa_source_coverage,
    fit_goa_surrogate,
    generate_goa_exploration_candidates,
    generate_goa_surrogate_candidates,
    goa_candidate_counts,
    goa_mutation_strength,
    load_goa_csv,
    load_goa_history,
    merge_goa_samples,
    predict_goa_metrics,
    sample_goa_parameters,
    score_goa_candidates,
    generate_repair_candidates,
)
from goa_eval.io_utils import write_json
from goa_eval.optimizer import load_param_space
from goa_eval.pareto import DEFAULT_OBJECTIVES, pareto_rank
from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


DEFAULT_STRATEGIES = ["random", "adaptive", "surrogate", "repair", "hybrid_goa"]

OUTPUT_REQUIRED_FILES = [
    "goa_strategy_benchmark.csv",
    "goa_strategy_benchmark_summary.json",
    "goa_strategy_leaderboard.csv",
    "goa_strategy_benchmark_report.md",
]

REQUIRED_BOUNDARY_FIELDS = {
    "benchmark_type": "goa_strategy_benchmark",
    "task_type": "candidate_quality_proxy",
    "data_source": "benchmark-derived",
    "engineering_validity": "simulation_only",
    "evidence_level": "csv-derived",
    "simulation_backend": "no_real_ngspice_required",
    "mock_used": False,
    "result_claim": "candidate_quality_proxy_only",
}


def run_goa_strategy_benchmark(
    *,
    history_path: Path | None,
    leaderboard_path: Path | None,
    param_space_path: Path,
    output_root: Path,
    strategies: list[str] | None = None,
    max_candidates: int = 30,
    seeds: list[int] | None = None,
    top_k: int = 10,
    objective_config: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if history_path is None and leaderboard_path is None:
        raise ValueError("At least one of --history or --leaderboard must be provided")
    strategies = strategies or DEFAULT_STRATEGIES
    seeds = seeds or [1, 2, 3]
    output_root.mkdir(parents=True, exist_ok=True)

    history = load_goa_history(history_path)
    leaderboard = load_goa_csv(leaderboard_path)
    samples = merge_goa_samples(history, leaderboard)
    param_space = load_param_space(param_space_path)
    param_names = list(param_space.keys())
    model_bundle = fit_goa_surrogate(samples, param_names)

    rows: list[dict[str, Any]] = []
    strategy_candidates: dict[str, dict[int, pd.DataFrame]] = {}

    for strategy in strategies:
        for seed in seeds:
            candidates = _generate_strategy_candidates(
                strategy=strategy,
                samples=samples,
                param_space=param_space,
                max_candidates=max_candidates,
                seed=seed,
                model_bundle=model_bundle,
            )
            candidate_frame = pd.DataFrame(candidates)
            if not candidate_frame.empty:
                candidate_frame = pareto_rank(candidate_frame)
            row = _benchmark_row(strategy, seed, candidate_frame, max_candidates, top_k, param_names, samples)
            rows.append(row)
            strategy_candidates.setdefault(strategy, {})[seed] = candidate_frame

    bench_frame = pd.DataFrame(rows)
    bench_frame.to_csv(output_root / "goa_strategy_benchmark.csv", index=False, encoding="utf-8-sig")

    summary = _build_summary(
        bench_frame,
        strategies=strategies,
        seeds=seeds,
        max_candidates=max_candidates,
        top_k=top_k,
        history_path=history_path,
        leaderboard_path=leaderboard_path,
        param_space_path=param_space_path,
        param_names=param_names,
        samples=samples,
        objective_config=objective_config,
    )
    write_json(output_root / "goa_strategy_benchmark_summary.json", summary)

    leaderboard = _build_leaderboard(summary)
    leaderboard.to_csv(output_root / "goa_strategy_leaderboard.csv", index=False, encoding="utf-8-sig")

    report_md = _build_report(summary, leaderboard)
    (output_root / "goa_strategy_benchmark_report.md").write_text(report_md, encoding="utf-8")

    _write_candidate_csvs(strategy_candidates, output_root)

    return summary


def generate_random_goa_candidates(
    param_space: dict[str, Any],
    max_candidates: int = 30,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates = []
    for index in range(max_candidates):
        params = sample_goa_parameters(param_space, rng)
        candidates.append(
            build_goa_candidate(
                source="random",
                parameters=params,
                changed_parameters=sorted(params.keys()),
                rationale="naive random baseline — no replay, no surrogate, no repair",
                model_status="random_no_replay",
                mutation_strength=1.0,
            )
        )
    return candidates


def generate_adaptive_goa_candidates(
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    max_candidates: int = 30,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    baseline = best_goa_parameters(samples, param_space)
    param_names = list(param_space.keys())
    candidates = []
    for _ in range(max_candidates):
        params = dict(baseline)
        for name in param_names:
            if rng.random() < 0.3:
                values = param_space.get(name, {}).get("values", [param_space.get(name)]) if isinstance(param_space.get(name), dict) else (param_space.get(name) if isinstance(param_space.get(name), list) else [param_space.get(name)])
                if values and isinstance(values, list):
                    params[name] = rng.choice(values)
        changed = changed_goa_parameters(baseline, params)
        candidates.append(
            build_goa_candidate(
                source="adaptive",
                parameters=params,
                changed_parameters=changed or sorted(params),
                rationale="rule-based adaptive candidate — small perturbation around history best",
                model_status="rule_based_adaptive",
                mutation_strength=goa_mutation_strength(baseline, params),
            )
        )
    return candidates


def generate_surrogate_goa_candidates(
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    model_bundle: dict[str, Any],
    max_candidates: int = 30,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return generate_goa_surrogate_candidates(samples, param_space, model_bundle, max_candidates, rng)


def generate_hybrid_goa_candidates(
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    model_bundle: dict[str, Any],
    max_candidates: int = 30,
    seed: int = 42,
    hybrid_candidate_mix: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    mix = hybrid_candidate_mix or {"surrogate": 0.5, "repair": 0.3, "exploration": 0.2}
    counts = goa_candidate_counts(max_candidates, mix)
    rng = random.Random(seed)
    param_names = list(param_space.keys())

    candidates: list[dict[str, Any]] = []
    candidates.extend(generate_goa_surrogate_candidates(samples, param_space, model_bundle, counts["surrogate"], rng))
    candidates.extend(generate_repair_candidates(samples, param_space, max_candidates=counts["repair"], seed=seed + 17))
    candidates.extend(generate_goa_exploration_candidates(samples, param_space, counts["exploration"], rng))
    candidates = ensure_goa_source_coverage(candidates, samples, param_space, model_bundle, rng, max_candidates)
    candidates = dedupe_goa_candidates(candidates)[:max_candidates]
    candidates = score_goa_candidates(candidates, samples, model_bundle, param_names)
    return candidates


def _generate_strategy_candidates(
    strategy: str,
    samples: pd.DataFrame,
    param_space: dict[str, Any],
    max_candidates: int,
    seed: int,
    model_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    if strategy == "random":
        return generate_random_goa_candidates(param_space, max_candidates=max_candidates, seed=seed)
    if strategy == "adaptive":
        return generate_adaptive_goa_candidates(samples, param_space, max_candidates=max_candidates, seed=seed)
    if strategy == "surrogate":
        return generate_surrogate_goa_candidates(samples, param_space, model_bundle, max_candidates=max_candidates, seed=seed)
    if strategy == "repair":
        return generate_repair_candidates(samples, param_space, max_candidates=max_candidates, seed=seed)
    if strategy in ("hybrid_goa", "physics_guided_hybrid"):
        return generate_hybrid_goa_candidates(samples, param_space, model_bundle, max_candidates=max_candidates, seed=seed)
    raise ValueError(f"Unknown strategy: {strategy}")


def _benchmark_row(
    strategy: str,
    seed: int,
    frame: pd.DataFrame,
    max_candidates: int,
    top_k: int,
    param_names: list[str],
    samples: pd.DataFrame,
) -> dict[str, Any]:
    candidate_count = len(frame)
    topk = frame.head(top_k) if not frame.empty else frame
    history_best_score = best_goa_score(samples) or 0.0

    source_counts = Counter(frame["candidate_source"]) if "candidate_source" in frame.columns and not frame.empty else Counter()
    total = candidate_count or 1

    return {
        "strategy": strategy,
        "seed": seed,
        "candidate_count": candidate_count,
        "max_candidates": max_candidates,
        "top_k": top_k,
        "data_source": "benchmark-derived",
        "engineering_validity": "simulation_only",
        "evidence_level": "csv-derived",
        "simulation_backend": "no_real_ngspice_required",
        "mock_used": False,
        "result_claim": "candidate_quality_proxy_only",
        "random_candidate_ratio": _safe_div(source_counts.get("random", 0), total),
        "adaptive_candidate_ratio": _safe_div(source_counts.get("adaptive", 0), total),
        "surrogate_candidate_ratio": _safe_div(source_counts.get("surrogate", 0), total),
        "repair_candidate_ratio": _safe_div(source_counts.get("repair", 0), total),
        "exploration_candidate_ratio": _safe_div(source_counts.get("exploration", 0), total),
        "best_predicted_score": _col_max(frame, "predicted_overall_score"),
        "topk_predicted_score_mean": _col_mean(topk, "predicted_overall_score"),
        "topk_candidate_quality_proxy_mean": _col_mean(topk, "candidate_quality_proxy"),
        "best_candidate_quality_proxy": _col_max(frame, "candidate_quality_proxy"),
        "predicted_score_gain_vs_history_best": (_col_max(frame, "predicted_overall_score") or 0.0) - history_best_score,
        "proxy_improvement_vs_random": 0.0,
        "best_predicted_Max_overlap_ratio": _col_min(frame, "predicted_Max_overlap_ratio"),
        "best_predicted_Max_ripple": _col_min(frame, "predicted_Max_ripple"),
        "best_predicted_Max_voltage_loss": _col_min(frame, "predicted_Max_voltage_loss"),
        "best_predicted_Delay_std": _col_min(frame, "predicted_Delay_std"),
        "topk_predicted_Max_overlap_ratio_mean": _col_mean(topk, "predicted_Max_overlap_ratio"),
        "topk_predicted_Max_ripple_mean": _col_mean(topk, "predicted_Max_ripple"),
        "topk_predicted_Max_voltage_loss_mean": _col_mean(topk, "predicted_Max_voltage_loss"),
        "topk_predicted_Delay_std_mean": _col_mean(topk, "predicted_Delay_std"),
        "pareto_front_hit_rate": _front_hit_rate(frame),
        "avg_pareto_rank": _col_mean(frame, "pareto_rank"),
        "best_pareto_rank": _col_min(frame, "pareto_rank"),
        "topk_pareto_rank_mean": _col_mean(topk, "pareto_rank"),
        "predicted_hard_constraint_pass_rate": _bool_rate(frame, "predicted_hard_constraint_passed"),
        "predicted_not_evaluable_rate": 1.0 - _bool_rate(frame, "predicted_hard_constraint_passed"),
        "repair_first_ratio": _style_ratio(frame, "repair_first"),
        "conservative_candidate_ratio": _style_ratio(frame, "conservative"),
        "candidate_diversity_score": _diversity_score(frame, param_names),
        "changed_parameter_coverage": _param_coverage(frame, param_names),
        "unique_candidate_ratio": _unique_ratio(frame),
    }


def _build_summary(
    frame: pd.DataFrame,
    *,
    strategies: list[str],
    seeds: list[int],
    max_candidates: int,
    top_k: int,
    history_path: Path | None,
    leaderboard_path: Path | None,
    param_space_path: Path,
    param_names: list[str],
    samples: pd.DataFrame,
    objective_config: list[dict[str, str]] | None,
) -> dict[str, Any]:
    metric_columns = []
    for col in ["Max_overlap_ratio", "Max_ripple", "Max_voltage_loss", "Delay_std", "overall_score", "hard_constraint_passed"]:
        if col in samples.columns:
            metric_columns.append(col)

    strategies_agg: dict[str, Any] = {}
    for strategy_name in strategies:
        group = frame[frame["strategy"] == strategy_name]
        if group.empty:
            strategies_agg[strategy_name] = _empty_strategy_metrics()
            continue
        strategies_agg[strategy_name] = {
            "best_predicted_score_mean": _json_number(group["best_predicted_score"].mean()),
            "topk_predicted_score_mean": _json_number(group["topk_predicted_score_mean"].mean()),
            "topk_candidate_quality_proxy_mean": _json_number(group["topk_candidate_quality_proxy_mean"].mean()),
            "best_predicted_score_max": _json_number(group["best_predicted_score"].max()),
            "predicted_score_gain_vs_history_best_mean": _json_number(group["predicted_score_gain_vs_history_best"].mean()),
            "pareto_front_hit_rate": _safe_mean(group, "pareto_front_hit_rate"),
            "avg_pareto_rank": _safe_mean(group, "avg_pareto_rank"),
            "topk_pareto_rank_mean": _safe_mean(group, "topk_pareto_rank_mean"),
            "predicted_hard_constraint_pass_rate": _safe_mean(group, "predicted_hard_constraint_pass_rate"),
            "candidate_diversity_score": _safe_mean(group, "candidate_diversity_score"),
            "changed_parameter_coverage": _safe_mean(group, "changed_parameter_coverage"),
            "unique_candidate_ratio": _safe_mean(group, "unique_candidate_ratio"),
            "repair_first_ratio": _safe_mean(group, "repair_first_ratio"),
            "surrogate_candidate_ratio": _safe_mean(group, "surrogate_candidate_ratio"),
            "repair_candidate_ratio": _safe_mean(group, "repair_candidate_ratio"),
            "exploration_candidate_ratio": _safe_mean(group, "exploration_candidate_ratio"),
            "random_candidate_ratio": _safe_mean(group, "random_candidate_ratio"),
            "adaptive_candidate_ratio": _safe_mean(group, "adaptive_candidate_ratio"),
            "seed_count": len(group),
        }
        proxy_improvement = _compute_proxy_improvement(strategies_agg, strategy_name, "random")
        strategies_agg[strategy_name]["proxy_improvement_vs_random"] = proxy_improvement

    _attach_random_proxy_inplace(frame, strategies_agg)

    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "benchmark_type": "goa_strategy_benchmark",
        "task_type": "candidate_quality_proxy",
        "data_source": "benchmark-derived",
        "engineering_validity": "simulation_only",
        "evidence_level": "csv-derived",
        "simulation_backend": "no_real_ngspice_required",
        "mock_used": False,
        "result_claim": "candidate_quality_proxy_only",
        "input_data": {
            "history": str(history_path) if history_path else "",
            "leaderboard": str(leaderboard_path) if leaderboard_path else "",
            "param_space": str(param_space_path),
            "row_count": len(samples),
            "parameter_columns": param_names,
            "metric_columns": metric_columns,
        },
        "fairness": {
            "same_input_history": bool(history_path),
            "same_input_leaderboard": bool(leaderboard_path),
            "same_param_space": True,
            "same_candidate_budget": max_candidates,
            "same_seed_set": seeds,
            "same_objective_config": objective_config or DEFAULT_OBJECTIVES,
            "same_top_k": top_k,
            "no_real_ngspice_required": True,
            "random_baseline_no_replay": True,
        },
        "strategy_groups": {
            "naive_baseline": ["random"],
            "engineering_baseline": ["adaptive"],
            "model_based": ["surrogate"],
            "repair_guided": ["repair"],
            "proposed": ["hybrid_goa", "physics_guided_hybrid"],
        },
        "strategies": strategies_agg,
        "leaderboard": [],
        "artifact_paths": {
            "benchmark_csv": "goa_strategy_benchmark.csv",
            "summary_json": "goa_strategy_benchmark_summary.json",
            "leaderboard_csv": "goa_strategy_leaderboard.csv",
            "report_md": "goa_strategy_benchmark_report.md",
        },
    }


def _build_leaderboard(summary: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for strategy, metrics in summary.get("strategies", {}).items():
        rows.append({"strategy": strategy, **metrics})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for col in [
        "predicted_hard_constraint_pass_rate",
        "pareto_front_hit_rate",
        "avg_pareto_rank",
        "topk_candidate_quality_proxy_mean",
        "candidate_diversity_score",
        "proxy_improvement_vs_random",
    ]:
        if col not in frame:
            frame[col] = 0.0
    return frame.sort_values(
        ["predicted_hard_constraint_pass_rate", "pareto_front_hit_rate", "avg_pareto_rank", "topk_candidate_quality_proxy_mean", "candidate_diversity_score"],
        ascending=[False, False, True, False, False],
        kind="mergesort",
    )


def _build_report(summary: dict[str, Any], leaderboard: pd.DataFrame) -> str:
    input_data = summary.get("input_data", {})
    fairness = summary.get("fairness", {})
    strategies_data = summary.get("strategies", {})

    lines = [
        "# GOA Strategy Benchmark Report",
        "",
        "data_source = benchmark-derived",
        "engineering_validity = simulation_only",
        "evidence_level = csv-derived",
        "simulation_backend = no_real_ngspice_required",
        "result_claim = candidate_quality_proxy_only",
        "",
        "## 1. Task Boundary",
        "",
        "- GOA-specific benchmark",
        "- simulation-only",
        "- benchmark-derived / csv-derived",
        "- no real ngspice required",
        "- candidate-quality proxy only",
        "- not physical validation",
        "",
        "## 2. Input Data",
        "",
        f"- History path: `{input_data.get('history', '')}`",
        f"- Leaderboard path: `{input_data.get('leaderboard', '')}`",
        f"- Param space path: `{input_data.get('param_space', '')}`",
        f"- Row count: `{input_data.get('row_count', 0)}`",
        f"- Parameter columns: `{', '.join(input_data.get('parameter_columns', []))}`",
        f"- Metric columns: `{', '.join(input_data.get('metric_columns', []))}`",
        "",
        "## 3. Compared Strategies",
        "",
        "- **random**: naive baseline — no replay, no surrogate, no repair",
        "- **adaptive**: engineering baseline — rule-based perturbation around history best",
        "- **surrogate**: model-based candidate ranking via sklearn RandomForest",
        "- **repair**: failure-guided repair search using GOA metric symptoms",
        "- **hybrid_goa**: surrogate + repair + exploration + Pareto ranking",
        "",
        "## 4. Fairness Rules",
        "",
        f"- same param space: `{fairness.get('same_param_space')}`",
        f"- same candidate budget: `{fairness.get('same_candidate_budget')}`",
        f"- same seeds: `{fairness.get('same_seed_set')}`",
        f"- same objective config: `{fairness.get('same_objective_config')}`",
        f"- random no replay: `{fairness.get('random_baseline_no_replay')}`",
        f"- no real ngspice required: `{fairness.get('no_real_ngspice_required')}`",
        "",
        "## 5. Metrics",
        "",
        "- **predicted score metrics**: surrogate-predicted overall_score (proxy only)",
        "- **GOA waveform proxy metrics**: predicted Max_overlap_ratio, Max_ripple, Max_voltage_loss, Delay_std",
        "- **Pareto metrics**: pareto_front_hit_rate, avg_pareto_rank, best_pareto_rank",
        "- **diversity metrics**: candidate_diversity_score, changed_parameter_coverage, unique_candidate_ratio",
        "- **hard constraint proxy metrics**: predicted_hard_constraint_pass_rate",
        "",
        "## 6. Strategy Leaderboard",
        "",
        "| strategy | best_predicted_score_mean | topk_candidate_quality_proxy_mean | pareto_front_hit_rate | avg_pareto_rank | predicted_hard_constraint_pass_rate | candidate_diversity_score | proxy_improvement_vs_random |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in leaderboard.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("strategy", "")),
                    _fmt(row.get("best_predicted_score_mean")),
                    _fmt(row.get("topk_candidate_quality_proxy_mean")),
                    _fmt(row.get("pareto_front_hit_rate")),
                    _fmt(row.get("avg_pareto_rank")),
                    _fmt(row.get("predicted_hard_constraint_pass_rate")),
                    _fmt(row.get("candidate_diversity_score")),
                    _fmt(row.get("proxy_improvement_vs_random")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 7. Engineering Interpretation",
            "",
            "- **hybrid_goa** results reflect candidate-quality proxy only, not validated simulation gain.",
            "- Leading performance means the proxy ranking pipeline prefers these candidates under the given data.",
            "- Next step: submit recommended candidates to GOA simulation or manual review.",
            "- Do not describe proxy improvement as `validated_gain`, `real_improvement`, or `silicon_verified`.",
            "",
            "Sorting priority: hard_constraint_pass_rate > pareto_front_hit_rate > avg_pareto_rank (lower) > topk_candidate_quality_proxy_mean > candidate_diversity_score.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_candidate_csvs(
    strategy_candidates: dict[str, dict[int, pd.DataFrame]],
    output_root: Path,
) -> None:
    candidates_dir = output_root / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    max_seeds = 3
    for strategy, seed_frames in strategy_candidates.items():
        for seed, frame in list(seed_frames.items())[:max_seeds]:
            if frame.empty:
                continue
            frame = complete_goa_output_columns(frame)
            frame.to_csv(candidates_dir / f"{strategy}_seed_{seed}.csv", index=False, encoding="utf-8-sig")


def _compute_proxy_improvement(
    strategies_agg: dict[str, Any],
    strategy_name: str,
    baseline_name: str,
) -> float:
    baseline = strategies_agg.get(baseline_name)
    current = strategies_agg.get(strategy_name)
    if not baseline or not current:
        return 0.0
    base_score = baseline.get("topk_candidate_quality_proxy_mean") or 0.0
    cur_score = current.get("topk_candidate_quality_proxy_mean") or 0.0
    if base_score <= 0:
        return 0.0
    return (cur_score - base_score) / base_score


def _attach_random_proxy_inplace(
    frame: pd.DataFrame,
    strategies_agg: dict[str, Any],
) -> None:
    random_rows = frame[frame["strategy"] == "random"]
    if random_rows.empty:
        return
    random_qp = _safe_mean(random_rows, "topk_candidate_quality_proxy_mean")
    if random_qp is None or random_qp <= 0:
        return
    for _, row in frame.iterrows():
        strategy = str(row.get("strategy", ""))
        idx = frame.index[frame["strategy"] == strategy].tolist()
        qp = _safe_mean(frame.loc[frame["strategy"] == strategy], "topk_candidate_quality_proxy_mean")
        if qp is None:
            continue
        improvement = (qp - random_qp) / random_qp
        for i in idx:
            frame.at[i, "proxy_improvement_vs_random"] = improvement


def _empty_strategy_metrics() -> dict[str, Any]:
    return {
        "best_predicted_score_mean": None,
        "topk_predicted_score_mean": None,
        "topk_candidate_quality_proxy_mean": None,
        "best_predicted_score_max": None,
        "predicted_score_gain_vs_history_best_mean": None,
        "pareto_front_hit_rate": 0.0,
        "avg_pareto_rank": None,
        "topk_pareto_rank_mean": None,
        "predicted_hard_constraint_pass_rate": 0.0,
        "candidate_diversity_score": 0.0,
        "changed_parameter_coverage": 0.0,
        "unique_candidate_ratio": 0.0,
        "repair_first_ratio": 0.0,
        "surrogate_candidate_ratio": 0.0,
        "repair_candidate_ratio": 0.0,
        "exploration_candidate_ratio": 0.0,
        "random_candidate_ratio": 0.0,
        "adaptive_candidate_ratio": 0.0,
        "seed_count": 0,
        "proxy_improvement_vs_random": 0.0,
    }


def _col_mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    return _json_number(pd.to_numeric(frame[column], errors="coerce").mean())


def _col_max(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    return _json_number(pd.to_numeric(frame[column], errors="coerce").max())


def _col_min(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    return _json_number(pd.to_numeric(frame[column], errors="coerce").min())


def _bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(frame[column].astype(bool).mean())


def _style_ratio(frame: pd.DataFrame, style: str) -> float:
    if frame.empty or "candidate_style" not in frame.columns:
        return 0.0
    total = len(frame) or 1
    return float((frame["candidate_style"].astype(str).str.lower() == style).sum()) / total


def _front_hit_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    col = "pareto_is_front"
    if col not in frame.columns:
        return 0.0
    front = frame[col]
    total = len(frame) or 1
    return float((front.astype(str).str.lower() == "true").sum()) / total


def _diversity_score(frame: pd.DataFrame, param_names: list[str]) -> float:
    if frame.empty or not param_names or "parameters_json" not in frame.columns:
        return 0.0
    unique_params = set()
    total = 0
    for _, row in frame.iterrows():
        params = _parse_json(row.get("parameters_json", "{}"))
        key = tuple(str(params.get(name, "")) for name in sorted(param_names))
        unique_params.add(key)
        total += 1
    if total == 0:
        return 0.0
    return len(unique_params) / total


def _param_coverage(frame: pd.DataFrame, param_names: list[str]) -> float:
    if frame.empty or not param_names:
        return 0.0
    covered = set()
    for _, row in frame.iterrows():
        for name in param_names:
            if name in str(row.get("changed_parameters", "")):
                covered.add(name)
    return len(covered) / len(param_names) if param_names else 0.0


def _unique_ratio(frame: pd.DataFrame) -> float:
    if frame.empty or "parameters_json" not in frame.columns:
        return 0.0
    keys = set()
    for _, row in frame.iterrows():
        keys.add(str(row.get("parameters_json", "")))
    return len(keys) / (len(frame) or 1)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _safe_mean(group: pd.DataFrame, column: str) -> float:
    if group.empty or column not in group.columns:
        return 0.0
    return float(pd.to_numeric(group[column], errors="coerce").fillna(0).mean())


def _json_number(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
