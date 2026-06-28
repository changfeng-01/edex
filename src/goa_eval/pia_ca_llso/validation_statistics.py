"""Aggregation helpers for PIA-CA-LLSO validation experiments."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


GROUP_COLUMNS = ["scenario_id", "method", "ablation", "budget"]


def summarize_validation_runs(run_summaries: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(run_summaries)
    if frame.empty:
        return pd.DataFrame()
    frame["target_hit"] = frame["target_hit"].astype(bool)
    grouped = frame.groupby(GROUP_COLUMNS, dropna=False)
    rows = []
    for key, group in grouped:
        target_times = pd.to_numeric(group["simulations_to_target"], errors="coerce")
        best_scores = pd.to_numeric(group["best_score_final"], errors="coerce")
        hit_values = group["target_hit"].astype(float)
        auc_values = pd.to_numeric(group["convergence_auc"], errors="coerce")
        hard_values = pd.to_numeric(group["hard_pass_rate"], errors="coerce")
        target_low, target_high = bootstrap_mean_ci(hit_values)
        target_times_low, target_times_high = bootstrap_mean_ci(target_times)
        auc_low, auc_high = bootstrap_mean_ci(auc_values)
        hard_low, hard_high = bootstrap_mean_ci(hard_values)
        rows.append(
            {
                **dict(zip(GROUP_COLUMNS, key)),
                "run_count": int(len(group)),
                "target_hit_rate": float(group["target_hit"].mean()),
                "target_hit_rate_ci_low": target_low,
                "target_hit_rate_ci_high": target_high,
                "best_score_mean": _mean(best_scores),
                "best_score_std": _std(best_scores),
                "best_score_var": _var(best_scores),
                "simulations_to_target_mean": _mean(target_times),
                "simulations_to_target_median": _median(target_times),
                "simulations_to_target_ci_low": target_times_low,
                "simulations_to_target_ci_high": target_times_high,
                "convergence_auc_mean": _mean(auc_values),
                "convergence_auc_std": _std(auc_values),
                "convergence_auc_var": _var(auc_values),
                "convergence_auc_ci_low": auc_low,
                "convergence_auc_ci_high": auc_high,
                "hard_pass_rate_mean": _mean(hard_values),
                "hard_pass_rate_std": _std(hard_values),
                "hard_pass_rate_var": _var(hard_values),
                "hard_pass_rate_ci_low": hard_low,
                "hard_pass_rate_ci_high": hard_high,
                "boundary_audit_pass_rate": float(group["boundary_audit_passed"].astype(bool).mean()),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        )
    return pd.DataFrame(rows)


def compute_pairwise_win_rates(summary_frame: pd.DataFrame, baseline: str = "random") -> pd.DataFrame:
    if summary_frame.empty:
        return pd.DataFrame()
    rows = []
    keys = ["scenario_id", "seed", "budget", "ablation"]
    for key, group in summary_frame.groupby(keys, dropna=False):
        for baseline_method, baseline_group in group.groupby("method", dropna=False):
            baseline_row = baseline_group.iloc[0]
            for _, row in group[group["method"] != baseline_method].iterrows():
                rows.append(
                    {
                        **dict(zip(keys, key)),
                        "baseline": baseline_method,
                        "method": row["method"],
                        "win": _wins(row, baseline_row),
                        "data_source": "real_simulation_csv",
                        "engineering_validity": "simulation_only",
                        "must_resimulate": True,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["method", "baseline", "budget", "ablation", "win_rate", f"win_rate_vs_{baseline}", "comparison_count"])
    comparisons = pd.DataFrame(rows)
    output = (
        comparisons.groupby(["method", "baseline", "budget", "ablation"], dropna=False)
        .agg(
            win=("win", "mean"),
            comparison_count=("win", "count"),
            data_source=("data_source", "first"),
            engineering_validity=("engineering_validity", "first"),
            must_resimulate=("must_resimulate", "first"),
        )
        .reset_index()
        .rename(columns={"win": "win_rate"})
    )
    compat_col = f"win_rate_vs_{baseline}"
    output[compat_col] = output["win_rate"].where(output["baseline"].astype(str) == str(baseline))
    output = output.sort_values(
        by=["method", "budget", "ablation", "baseline"],
        key=lambda column: column.astype(str).map(lambda value: f"0_{value}" if value == str(baseline) else f"1_{value}"),
    ).reset_index(drop=True)
    return output


def bootstrap_mean_ci(values: Sequence[float], seed: int = 42, n_boot: int = 1000) -> tuple[float, float]:
    clean = np.array([float(value) for value in values if pd.notna(value)], dtype=float)
    if clean.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.RandomState(seed)
    means = [float(rng.choice(clean, size=clean.size, replace=True).mean()) for _ in range(n_boot)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _wins(row: pd.Series, baseline_row: pd.Series) -> bool:
    row_hit = bool(row.get("target_hit", False))
    base_hit = bool(baseline_row.get("target_hit", False))
    if row_hit and base_hit:
        return _numeric(row.get("simulations_to_target"), float("inf")) < _numeric(
            baseline_row.get("simulations_to_target"),
            float("inf"),
        )
    if row_hit != base_hit:
        return row_hit
    return _numeric(row.get("best_score_final"), float("-inf")) > _numeric(
        baseline_row.get("best_score_final"),
        float("-inf"),
    )


def _numeric(value: object, default: float) -> float:
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.mean()) if not clean.empty else float("nan")


def _std(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.std(ddof=0)) if not clean.empty else float("nan")


def _var(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.var(ddof=0)) if not clean.empty else float("nan")


def _median(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.median()) if not clean.empty else float("nan")
