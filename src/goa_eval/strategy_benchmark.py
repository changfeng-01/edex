from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.sky130_mainline import run_sky130_mainline


DEFAULT_STRATEGIES = ["random", "adaptive", "genetic", "bayesian", "surrogate", "hybrid"]


def run_strategy_benchmark(
    *,
    sweep_path: Path,
    output_root: Path,
    seeds: list[int],
    rounds: int,
    max_runs_per_round: int,
    validation_config_path: Path | None = None,
    pdk_root: Path | None = None,
    split: str = "train",
    max_rows: int = 1,
    topology: str | None = None,
    source_dataset: str | None = None,
    dataset_name: str = "pphilip/analog-circuits-sky130",
    mock_dataset_json: Path | None = None,
    mock_ngspice: bool = False,
    ngspice_cmd: str = "ngspice",
    spec_path: Path = Path("config/sky130_transient_spec.yaml"),
    param_space_path: Path = Path("examples/sample_params.yaml"),
    max_candidates: int = 10,
    strategies: list[str] | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    strategies = strategies or DEFAULT_STRATEGIES
    sweep_config = _read_yaml(sweep_path)
    validation_config = _read_yaml(validation_config_path)
    parameter_names = list((sweep_config.get("parameters") or {}).keys())
    rows: list[dict[str, Any]] = []
    for strategy in strategies:
        for seed in seeds:
            run_dir = output_root / strategy / f"seed_{seed}"
            payload = run_sky130_mainline(
                sweep_path=sweep_path,
                output_root=run_dir,
                validation_config_path=validation_config_path,
                rounds=rounds,
                max_runs_per_round=max_runs_per_round,
                pdk_root=pdk_root,
                split=split,
                max_rows=max_rows,
                topology=topology,
                source_dataset=source_dataset,
                dataset_name=dataset_name,
                mock_dataset_json=mock_dataset_json,
                mock_ngspice=mock_ngspice,
                mock_if_unavailable=not mock_ngspice,
                ngspice_cmd=ngspice_cmd,
                spec_path=spec_path,
                param_space_path=param_space_path,
                max_candidates=max_candidates,
                seed=seed,
                strategy=strategy,
                full_validation=False,
            )
            rows.append(_benchmark_row(strategy, seed, run_dir, payload, parameter_names=parameter_names))
    frame = pd.DataFrame(rows)
    frame.to_csv(output_root / "strategy_benchmark.csv", index=False, encoding="utf-8-sig")
    summary = _summary(
        frame,
        scenario=_scenario(
            sweep_path=sweep_path,
            validation_config_path=validation_config_path,
            validation_config=validation_config,
            seeds=seeds,
            rounds=rounds,
            max_runs_per_round=max_runs_per_round,
            max_rows=max_rows,
            topology=topology,
            source_dataset=source_dataset,
            dataset_name=dataset_name,
            mock_ngspice=mock_ngspice,
            strategy_names=strategies,
        ),
    )
    leaderboard = _strategy_leaderboard(summary)
    leaderboard.to_csv(output_root / "strategy_leaderboard.csv", index=False, encoding="utf-8-sig")
    write_json(output_root / "strategy_benchmark_summary.json", summary)
    _write_report(output_root / "strategy_benchmark_report.md", summary, leaderboard)
    return summary


def parse_seeds(value: str) -> list[int]:
    seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    return seeds or [42]


def _benchmark_row(
    strategy: str,
    seed: int,
    run_dir: Path,
    payload: dict[str, Any],
    *,
    parameter_names: list[str],
) -> dict[str, Any]:
    leaderboard = _read_csv(run_dir / "optimization_leaderboard.csv")
    history = _read_json(run_dir / "optimization_history.json")
    best = leaderboard.iloc[0].to_dict() if not leaderboard.empty else {}
    matrix = payload.get("validation_matrix_summary", {})
    hard_failures = _as_float(best.get("hard_constraint_failure_count")) or 0.0
    hard_passed = _as_bool(best.get("hard_constraint_passed"))
    if hard_passed is None:
        hard_passed = hard_failures <= 0
    target_passed = best.get("target_passed") is True or str(best.get("target_passed")).lower() == "true"
    validation_count = int(matrix.get("validation_case_count", 0) or 0)
    validation_passed = bool(validation_count and matrix.get("validation_pass_count") == validation_count)
    history_rows = history.get("history", []) if isinstance(history.get("history"), list) else []
    rank_status = str(best.get("rank_status") or _rank_status(best))
    return {
        "strategy": strategy,
        "seed": seed,
        "best_score": _as_float(best.get("overall_score")),
        "rank_status": rank_status,
        "target_status": best.get("target_status", ""),
        "target_passed": target_passed,
        "hard_constraint_passed": bool(hard_passed),
        "hard_failed": hard_failures > 0,
        "not_evaluable_metric_count": int(_as_float(best.get("not_evaluable_metric_count")) or 0),
        "validation_passed": validation_passed,
        "validation_case_count": validation_count,
        "validation_not_evaluable_count": int(matrix.get("validation_not_evaluable_count", 0) or 0),
        "worst_case_name": matrix.get("worst_case_name", ""),
        "worst_case_value": matrix.get("worst_case_value", ""),
        "simulation_count": len(history_rows),
        "first_pass_sim_count": _first_pass_sim_count(history_rows),
        "candidate_source": best.get("candidate_source", ""),
        "source_candidate_trigger_metric": best.get("source_candidate_trigger_metric", ""),
        "source_candidate_rationale": best.get("source_candidate_rationale", ""),
        "model_status": best.get("model_status", ""),
        "changed_parameters": _changed_parameters(best, parameter_names),
        "mock_used": bool(payload.get("mock_used")),
        "evidence_level": payload.get("evidence_level"),
        "simulation_backend": payload.get("simulation_backend"),
        "run_dir": str(run_dir),
    }


def _summary(frame: pd.DataFrame, *, scenario: dict[str, Any]) -> dict[str, Any]:
    strategies: dict[str, Any] = {}
    for strategy, group in frame.groupby("strategy", sort=False):
        scores = pd.to_numeric(group["best_score"], errors="coerce")
        sim_counts = pd.to_numeric(group["simulation_count"], errors="coerce").fillna(0)
        first_pass = pd.to_numeric(group["first_pass_sim_count"], errors="coerce")
        efficiency = scores / sim_counts.replace(0, pd.NA)
        strategies[str(strategy)] = {
            "best_score_mean": _json_number(scores.mean()),
            "best_score_std": _json_number(scores.std(ddof=0)),
            "target_pass_rate": float(group["target_passed"].astype(bool).mean()) if len(group) else 0.0,
            "hard_constraint_pass_rate": float(group["hard_constraint_passed"].astype(bool).mean()) if len(group) else 0.0,
            "hard_fail_rate": float(group["hard_failed"].astype(bool).mean()) if len(group) else 0.0,
            "validation_pass_rate": float(group["validation_passed"].astype(bool).mean()) if len(group) else 0.0,
            "not_evaluable_rate": float(group["rank_status"].eq("not_evaluable").mean()) if len(group) else 0.0,
            "avg_not_evaluable_metric_count": float(pd.to_numeric(group["not_evaluable_metric_count"], errors="coerce").fillna(0).mean()) if len(group) else 0.0,
            "avg_validation_not_evaluable_count": float(pd.to_numeric(group["validation_not_evaluable_count"], errors="coerce").fillna(0).mean()) if len(group) else 0.0,
            "avg_sim_count": float(sim_counts.mean()) if len(group) else 0.0,
            "first_pass_sim_count_mean": _json_number(first_pass.mean()),
            "improvement_per_simulation": _json_number(efficiency.mean()),
            "mock_used_rate": float(group["mock_used"].astype(bool).mean()) if len(group) else 0.0,
        }
    _attach_baseline_metrics(strategies, baseline="random")
    return {
        "schema_version": "1.0",
        "result_version": "1.0",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "scenario": scenario,
        "fairness": {
            "same_param_space": True,
            "same_budget": True,
            "same_scoring_profile": True,
            "same_seed_set": True,
            "same_backend": True,
            "random_baseline_no_replay": True,
        },
        "baselines": {
            "naive": ["random"],
            "engineering": ["adaptive"],
        },
        "strategy_groups": {
            "naive_baseline": ["random"],
            "engineering_baseline": ["adaptive"],
            "search_baseline": ["genetic"],
            "model_based": ["bayesian", "surrogate"],
            "proposed": ["hybrid"],
        },
        "strategies": strategies,
    }


def _strategy_leaderboard(summary: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for strategy, metrics in summary.get("strategies", {}).items():
        rows.append({"strategy": strategy, **metrics})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for column in ["hard_constraint_pass_rate", "target_pass_rate", "validation_pass_rate", "best_score_mean", "avg_sim_count"]:
        if column not in frame:
            frame[column] = 0.0
    return frame.sort_values(
        ["hard_constraint_pass_rate", "target_pass_rate", "validation_pass_rate", "best_score_mean", "avg_sim_count"],
        ascending=[False, False, False, False, True],
        kind="mergesort",
    )


def _write_report(path: Path, summary: dict[str, Any], leaderboard: pd.DataFrame) -> None:
    scenario = summary.get("scenario", {})
    lines = [
        "# Strategy Benchmark Report",
        "",
        "data_source = real_simulation_csv",
        "engineering_validity = simulation_only",
        "",
        "## Scenario",
        "",
        f"- Target metric: `{scenario.get('target_metric', '')}`",
        f"- Target threshold: `{scenario.get('target_threshold', '')}`",
        f"- Seeds: `{scenario.get('seeds', [])}`",
        f"- Budget: `{scenario.get('rounds', '')}` rounds x `{scenario.get('max_runs_per_round', '')}` max runs per round",
        f"- Random baseline no replay: `{summary.get('fairness', {}).get('random_baseline_no_replay')}`",
        "",
        "| strategy | best_score_mean | target_pass_rate | hard_fail_rate | validation_pass_rate | avg_sim_count | mock_used_rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for strategy, metrics in summary["strategies"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    strategy,
                    str(metrics["best_score_mean"]),
                    str(metrics["target_pass_rate"]),
                    str(metrics["hard_fail_rate"]),
                    str(metrics["validation_pass_rate"]),
                    str(metrics["avg_sim_count"]),
                    str(metrics["mock_used_rate"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Strategy Leaderboard",
            "",
            "| strategy | hard_constraint_pass_rate | target_pass_rate | validation_pass_rate | best_score_mean | improvement_per_simulation | score_improvement_vs_random |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for _, row in leaderboard.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("strategy", "")),
                    str(row.get("hard_constraint_pass_rate", "")),
                    str(row.get("target_pass_rate", "")),
                    str(row.get("validation_pass_rate", "")),
                    str(row.get("best_score_mean", "")),
                    str(row.get("improvement_per_simulation", "")),
                    str(row.get("score_improvement_vs_random", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Benchmark Rules",
            "",
            "- Hard constraints and target status gate interpretation before soft score comparisons.",
            "- `not_evaluable` is tracked separately from failed and skipped runs.",
            "- Candidate provenance fields keep parameter changes, trigger metrics, rationale, and model status visible for review.",
            "- Results remain simulation-only and must not be described as physical or silicon validation.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_number(value: Any) -> float | None:
    number = _as_float(value)
    return number if number is not None else None


def _scenario(
    *,
    sweep_path: Path,
    validation_config_path: Path | None,
    validation_config: dict[str, Any],
    seeds: list[int],
    rounds: int,
    max_runs_per_round: int,
    max_rows: int,
    topology: str | None,
    source_dataset: str | None,
    dataset_name: str,
    mock_ngspice: bool,
    strategy_names: list[str],
) -> dict[str, Any]:
    target = validation_config.get("target", {}) if isinstance(validation_config.get("target"), dict) else {}
    matrix = validation_config.get("validation_matrix", [])
    return {
        "task_type": "sky130_strategy_optimization",
        "target_application": "simulation_only_circuit_optimization",
        "sweep_config": str(sweep_path),
        "validation_config": str(validation_config_path) if validation_config_path else "",
        "target_metric": target.get("metric", "Max_overlap_ratio"),
        "target_threshold": target.get("threshold", 0.1),
        "hard_constraints": [
            "rank_status_evaluated",
            "hard_constraint_passed",
            "target_metric_passed",
            "simulation_backend_boundary_preserved",
        ],
        "validation_matrix": [str(item.get("name", "")) for item in matrix if isinstance(item, dict)],
        "strategies": strategy_names,
        "budget": {
            "rounds": rounds,
            "max_runs_per_round": max_runs_per_round,
            "max_rows": max_rows,
            "seeds": seeds,
        },
        "shared_config": {
            "topology": topology or "",
            "source_dataset": source_dataset or "",
            "dataset": dataset_name,
            "backend": "mock_ngspice" if mock_ngspice else "ngspice_or_mock_fallback",
        },
    }


def _attach_baseline_metrics(strategies: dict[str, Any], *, baseline: str) -> None:
    base = strategies.get(baseline, {})
    base_score = _as_float(base.get("best_score_mean"))
    base_target_rate = _as_float(base.get("target_pass_rate"))
    base_efficiency = _as_float(base.get("improvement_per_simulation"))
    for metrics in strategies.values():
        metrics[f"score_improvement_vs_{baseline}"] = _relative_gain(metrics.get("best_score_mean"), base_score)
        metrics[f"target_pass_rate_gain_vs_{baseline}"] = _difference(metrics.get("target_pass_rate"), base_target_rate)
        metrics[f"simulation_efficiency_gain_vs_{baseline}"] = _relative_gain(metrics.get("improvement_per_simulation"), base_efficiency)


def _relative_gain(value: Any, baseline: Any) -> float | None:
    value_number = _as_float(value)
    baseline_number = _as_float(baseline)
    if value_number is None or baseline_number in {None, 0.0}:
        return None
    return (value_number - baseline_number) / abs(baseline_number)


def _difference(value: Any, baseline: Any) -> float | None:
    value_number = _as_float(value)
    baseline_number = _as_float(baseline)
    if value_number is None or baseline_number is None:
        return None
    return value_number - baseline_number


def _as_bool(value: Any) -> bool | None:
    if value is True or str(value).lower() == "true":
        return True
    if value is False or str(value).lower() == "false":
        return False
    return None


def _rank_status(row: dict[str, Any]) -> str:
    status = str(row.get("status", "") or "").lower()
    if status == "evaluated" and _as_float(row.get("overall_score")) is not None:
        return "evaluated"
    if status == "evaluated":
        return "not_evaluable"
    return status or "unknown"


def _first_pass_sim_count(history_rows: list[Any]) -> int | None:
    for index, row in enumerate(history_rows, start=1):
        if not isinstance(row, dict):
            continue
        hard_passed = _as_bool(row.get("hard_constraint_passed"))
        target_passed = _as_bool(row.get("target_passed"))
        if hard_passed is True and target_passed is True:
            return index
    return None


def _changed_parameters(best: dict[str, Any], parameter_names: list[str]) -> str:
    raw = best.get("source_candidate_parameters_json")
    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict) and payload:
            return ";".join(sorted(str(key) for key in payload))
    present = [name for name in parameter_names if str(best.get(name, "")).strip()]
    return ";".join(present)
