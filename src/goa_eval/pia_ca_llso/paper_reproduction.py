from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.paper_baselines import (
    PAPER_BASELINE_STRATEGIES,
    build_reproduction_cards,
    sanitize_candidate_pool,
)
from goa_eval.pia_ca_llso.selector import select_candidates


DEFAULT_REPRODUCTION_METHODS = (
    "classifier_level_hybrid",
    *PAPER_BASELINE_STRATEGIES,
)


def run_paper_reproduction_benchmark(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    output_dir: str | Path,
    methods: Sequence[str] | None = None,
    target_score: float = 80.0,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    labeled_history = assign_level_labels(history)
    ranking_candidates = sanitize_candidate_pool(candidates)
    evidence = _candidate_evidence(candidates)
    active_methods = list(methods or DEFAULT_REPRODUCTION_METHODS)

    run_rows = []
    summary_rows = []
    curves = {}
    for method in active_methods:
        selected = _select_method(method, labeled_history, ranking_candidates, candidates, top_k=top_k, config=config)
        selected = _attach_imported_evidence(selected, evidence)
        selected["method"] = method
        selected["budget_index"] = range(1, len(selected) + 1)
        selected["data_source"] = "real_simulation_csv"
        selected["engineering_validity"] = "simulation_only"
        selected["must_resimulate"] = True
        metrics = _method_metrics(selected, target_score=target_score)
        curves[method] = metrics.pop("convergence_curve")
        summary_rows.append({"method": method, **metrics})
        run_rows.extend(selected.to_dict("records"))

    runs = pd.DataFrame(run_rows)
    summary = pd.DataFrame(summary_rows)
    win_rates = _pairwise_win_rates(summary)

    cards = build_reproduction_cards()
    (out / "paper_reproduction_cards.json").write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    runs.to_csv(out / "paper_baseline_runs.csv", index=False)
    summary.to_csv(out / "paper_baseline_summary.csv", index=False)
    win_rates.to_csv(out / "paper_baseline_win_rates.csv", index=False)
    (out / "paper_reproduction_report.md").write_text(
        render_paper_reproduction_report(summary, win_rates, active_methods, target_score),
        encoding="utf-8",
    )
    result = {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "claim_boundary": "faithful GOA reimplementation, not original paper benchmark reproduction",
        "methods": active_methods,
        "target_score": target_score,
        "outputs": [
            "paper_reproduction_cards.json",
            "paper_baseline_runs.csv",
            "paper_baseline_summary.csv",
            "paper_baseline_win_rates.csv",
            "paper_reproduction_report.md",
        ],
    }
    (out / "paper_reproduction_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _select_method(
    method: str,
    labeled_history: pd.DataFrame,
    ranking_candidates: pd.DataFrame,
    original_candidates: pd.DataFrame,
    top_k: int,
    config: Mapping[str, Any] | None,
) -> pd.DataFrame:
    if method in {"classifier_level_hybrid", "pia_full", "pia_no_repair"}:
        from goa_eval.pia_ca_llso.loop import suggest_next_run
        active_config = dict(config or {})
        if method == "pia_no_repair":
            active_config.setdefault("repair_candidates", {})["enabled"] = False

        return suggest_next_run(
            labeled_history,
            original_candidates,
            active_config,
            strategy="classifier_level_hybrid",
            top_k=top_k,
        ).selected_candidates.copy()
    return select_candidates(ranking_candidates, labeled_history, strategy=method, top_k=top_k, config=config).selected_candidates.copy()


def render_paper_reproduction_report(
    summary: pd.DataFrame,
    win_rates: pd.DataFrame,
    methods: Sequence[str],
    target_score: float,
) -> str:
    lines = [
        "# PIA-CA-LLSO Paper Baseline Reproduction",
        "",
        "This report uses a unified GOA/PIA simulation-only protocol. It is not a reproduction of the original paper benchmark tables.",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- fidelity_level = faithful_goa_reimplementation",
        "- claim_boundary = not_original_paper_benchmark_reproduction",
        "",
        f"Target score: {target_score}",
        "",
        "| Method | Target Hit Rate | Simulations To Target | Convergence AUC | Best Evidence Score |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in summary.iterrows():
        simulations_to_target = row.get("simulations_to_target", "")
        if pd.isna(simulations_to_target):
            simulations_to_target = ""
        lines.append(
            f"| {row['method']} | {float(row.get('target_hit_rate', 0.0)):.3f} | "
            f"{simulations_to_target} | {float(row.get('convergence_auc', 0.0)):.3f} | "
            f"{row.get('best_evidence_score', '')} |"
        )
    lines.extend(
        [
            "",
            "## Method Set",
            "",
            ", ".join(methods),
            "",
            "## Win Rates",
            "",
            "| Method | Win Rate |",
            "|---|---:|",
        ]
    )
    for _, row in win_rates.iterrows():
        lines.append(f"| {row['method']} | {float(row.get('win_rate', 0.0)):.3f} |")
    lines.extend(
        [
            "",
            "Conclusion rule: only claim PIA superiority when it wins on most scenarios/seeds under the same imported simulation budget. "
            "If repair ablations do not improve the metrics, constraint-ledger repair remains a heuristic module.",
            "",
        ]
    )
    return "\n".join(lines)


def _candidate_evidence(candidates: pd.DataFrame) -> pd.DataFrame:
    if "candidate_id" not in candidates.columns:
        return pd.DataFrame(columns=["candidate_id"])
    evidence_cols = [
        column
        for column in [
            "candidate_id",
            "overall_score",
            "hard_constraint_passed",
            "sim_success",
            "status",
            "constraint_violation",
        ]
        if column in candidates.columns
    ]
    return candidates[evidence_cols].copy()


def _attach_imported_evidence(selected: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    selected = selected.drop(
        columns=[
            column
            for column in [
                "overall_score",
                "hard_constraint_passed",
                "sim_success",
                "status",
                "constraint_violation",
            ]
            if column in selected.columns
        ],
        errors="ignore",
    )
    if evidence.empty or "candidate_id" not in selected.columns:
        output = selected.copy()
        output["simulation_evidence_available"] = False
        return output
    output = selected.merge(evidence, on="candidate_id", how="left", suffixes=("", "_evidence"))
    if "overall_score" in output.columns:
        output["simulation_evidence_score"] = pd.to_numeric(output["overall_score"], errors="coerce")
        output = output.drop(columns=["overall_score"])
    else:
        output["simulation_evidence_score"] = np.nan
    if "hard_constraint_passed" in output.columns:
        output["simulation_evidence_hard_pass"] = output["hard_constraint_passed"].astype("boolean")
        output = output.drop(columns=["hard_constraint_passed"])
    else:
        output["simulation_evidence_hard_pass"] = pd.Series(pd.NA, index=output.index, dtype="boolean")
    output["simulation_evidence_available"] = output["simulation_evidence_score"].notna()
    return output


def _method_metrics(selected: pd.DataFrame, target_score: float) -> dict[str, Any]:
    scores = pd.to_numeric(selected.get("simulation_evidence_score", pd.Series(dtype=float)), errors="coerce")
    hard = selected.get("simulation_evidence_hard_pass", pd.Series(False, index=selected.index)).fillna(False).astype(bool)
    feasible_scores = scores.where(hard, other=np.nan)
    curve = feasible_scores.cummax().fillna(0.0).tolist()
    target_hits = [idx + 1 for idx, value in enumerate(curve) if value >= target_score]
    return {
        "selected_count": int(len(selected)),
        "target_hit_rate": float(((scores >= target_score) & hard).mean()) if len(selected) else 0.0,
        "simulations_to_target": target_hits[0] if target_hits else np.nan,
        "convergence_auc": float(np.trapezoid(curve)) if len(curve) > 1 else float(curve[0]) if curve else 0.0,
        "best_evidence_score": float(np.nanmax(feasible_scores)) if not feasible_scores.isna().all() else np.nan,
        "mean_acquisition_score": float(
            pd.to_numeric(
                selected.get("acquisition_score", pd.Series(0.0, index=selected.index)),
                errors="coerce",
            )
            .fillna(0.0)
            .mean()
        ),
        "convergence_curve": [float(value) for value in curve],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }


def _pairwise_win_rates(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, left in summary.iterrows():
        wins = 0
        total = 0
        for _, right in summary.iterrows():
            if left["method"] == right["method"]:
                continue
            total += 1
            if _dominates(left, right):
                wins += 1
        rows.append({"method": left["method"], "win_rate": float(wins / total) if total else 0.0, "comparisons": total})
    return pd.DataFrame(rows)


def _dominates(left: pd.Series, right: pd.Series) -> bool:
    left_budget = left.get("simulations_to_target")
    right_budget = right.get("simulations_to_target")
    if pd.notna(left_budget) and pd.isna(right_budget):
        return True
    if pd.notna(left_budget) and pd.notna(right_budget) and float(left_budget) < float(right_budget):
        return True
    if float(left.get("target_hit_rate", 0.0)) > float(right.get("target_hit_rate", 0.0)):
        return True
    return float(left.get("convergence_auc", 0.0)) > float(right.get("convergence_auc", 0.0))
