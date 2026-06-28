from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.validation_statistics import (
    bootstrap_mean_ci,
    compute_pairwise_win_rates,
    summarize_validation_runs,
)


def _runs() -> list[dict]:
    return [
        {
            "scenario_id": "s1",
            "method": "random",
            "ablation": "full",
            "seed": 1,
            "budget": 8,
            "target_hit": False,
            "simulations_to_target": None,
            "best_score_final": 75.0,
            "convergence_auc": 70.0,
            "hard_pass_rate": 0.5,
            "boundary_audit_passed": True,
        },
        {
            "scenario_id": "s1",
            "method": "pia_evolve_full",
            "ablation": "full",
            "seed": 1,
            "budget": 8,
            "target_hit": True,
            "simulations_to_target": 4,
            "best_score_final": 88.0,
            "convergence_auc": 82.0,
            "hard_pass_rate": 1.0,
            "boundary_audit_passed": True,
        },
    ]


def test_statistics_compute_mean_std_and_hit_rate() -> None:
    frame = summarize_validation_runs(_runs())

    row = frame[frame["method"] == "pia_evolve_full"].iloc[0]
    assert row["target_hit_rate"] == 1.0
    assert row["target_hit_rate_ci_low"] <= row["target_hit_rate_ci_high"]
    assert row["best_score_mean"] == 88.0
    assert row["best_score_var"] == 0.0
    assert row["boundary_audit_pass_rate"] == 1.0
    assert row["engineering_validity"] == "simulation_only"


def test_statistics_compute_convergence_auc_from_curve() -> None:
    frame = summarize_validation_runs(_runs())

    assert "convergence_auc_mean" in frame.columns
    assert "convergence_auc_ci_low" in frame.columns
    assert "hard_pass_rate_ci_high" in frame.columns
    assert frame["convergence_auc_mean"].notna().all()


def test_statistics_compute_nonparametric_win_rate() -> None:
    rates = compute_pairwise_win_rates(pd.DataFrame(_runs()), baseline="random")

    row = rates[rates["method"] == "pia_evolve_full"].iloc[0]
    assert row["baseline"] == "random"
    assert row["win_rate"] == 1.0
    assert row["win_rate_vs_random"] == 1.0
    assert row["engineering_validity"] == "simulation_only"


def test_statistics_compute_all_pairs_win_rate() -> None:
    runs = _runs() + [
        {
            "scenario_id": "s1",
            "method": "pia_capm_distance",
            "ablation": "full",
            "seed": 1,
            "budget": 8,
            "target_hit": False,
            "simulations_to_target": None,
            "best_score_final": 77.0,
            "convergence_auc": 72.0,
            "hard_pass_rate": 0.5,
            "boundary_audit_passed": True,
        },
    ]

    rates = compute_pairwise_win_rates(pd.DataFrame(runs), baseline="random")

    assert {"random", "pia_capm_distance"} <= set(rates["baseline"])
    assert ((rates["method"] == "pia_evolve_full") & (rates["baseline"] == "pia_capm_distance")).any()


def test_statistics_handles_missing_target_hits() -> None:
    frame = summarize_validation_runs(_runs())

    random_row = frame[frame["method"] == "random"].iloc[0]
    assert pd.isna(random_row["simulations_to_target_mean"])


def test_bootstrap_mean_ci_returns_ordered_bounds() -> None:
    low, high = bootstrap_mean_ci([1.0, 2.0, 3.0], seed=1, n_boot=100)

    assert low <= high
