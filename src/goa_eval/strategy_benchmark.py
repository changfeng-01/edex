from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

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
            rows.append(_benchmark_row(strategy, seed, run_dir, payload))
    frame = pd.DataFrame(rows)
    frame.to_csv(output_root / "strategy_benchmark.csv", index=False, encoding="utf-8-sig")
    summary = _summary(frame)
    write_json(output_root / "strategy_benchmark_summary.json", summary)
    _write_report(output_root / "strategy_benchmark_report.md", summary)
    return summary


def parse_seeds(value: str) -> list[int]:
    seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    return seeds or [42]


def _benchmark_row(strategy: str, seed: int, run_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    leaderboard = _read_csv(run_dir / "optimization_leaderboard.csv")
    history = _read_json(run_dir / "optimization_history.json")
    best = leaderboard.iloc[0].to_dict() if not leaderboard.empty else {}
    matrix = payload.get("validation_matrix_summary", {})
    hard_failures = _as_float(best.get("hard_constraint_failure_count")) or 0.0
    target_passed = best.get("target_passed") is True or str(best.get("target_passed")).lower() == "true"
    validation_count = int(matrix.get("validation_case_count", 0) or 0)
    validation_passed = bool(validation_count and matrix.get("validation_pass_count") == validation_count)
    return {
        "strategy": strategy,
        "seed": seed,
        "best_score": _as_float(best.get("overall_score")),
        "target_passed": target_passed,
        "hard_failed": hard_failures > 0,
        "validation_passed": validation_passed,
        "validation_case_count": validation_count,
        "simulation_count": len(history.get("history", [])) if isinstance(history.get("history"), list) else 0,
        "mock_used": bool(payload.get("mock_used")),
        "evidence_level": payload.get("evidence_level"),
        "simulation_backend": payload.get("simulation_backend"),
        "run_dir": str(run_dir),
    }


def _summary(frame: pd.DataFrame) -> dict[str, Any]:
    strategies: dict[str, Any] = {}
    for strategy, group in frame.groupby("strategy", sort=False):
        scores = pd.to_numeric(group["best_score"], errors="coerce")
        strategies[str(strategy)] = {
            "best_score_mean": _json_number(scores.mean()),
            "best_score_std": _json_number(scores.std(ddof=0)),
            "target_pass_rate": float(group["target_passed"].astype(bool).mean()) if len(group) else 0.0,
            "hard_fail_rate": float(group["hard_failed"].astype(bool).mean()) if len(group) else 0.0,
            "validation_pass_rate": float(group["validation_passed"].astype(bool).mean()) if len(group) else 0.0,
            "avg_sim_count": float(pd.to_numeric(group["simulation_count"], errors="coerce").fillna(0).mean()) if len(group) else 0.0,
            "mock_used_rate": float(group["mock_used"].astype(bool).mean()) if len(group) else 0.0,
        }
    return {"strategies": strategies}


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Strategy Benchmark Report",
        "",
        "data_source = real_simulation_csv",
        "engineering_validity = simulation_only",
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
