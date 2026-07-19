from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.selector import select_candidates


def compute_run_metrics(scored: pd.DataFrame, target_score: float = 80) -> dict[str, float | int | None | list[float]]:
    if scored.empty:
        return {
            "best_feasible_score_under_budget": None,
            "convergence_curve": [],
            "convergence_auc": 0.0,
            "first_feasible_eval": None,
            "fe_at_target": None,
            "hard_constraint_pass_rate": 0.0,
            "not_evaluable_rate": 0.0,
            "simulation_failure_rate": 0.0,
            "mean_violation": 0.0,
            "candidate_hit_rate": 0.0,
            "l1_discovery_count": 0,
            "enrichment_factor": 0.0,
        }
    frame = scored.copy()
    hard_col = "hard_pass" if "hard_pass" in frame.columns else "hard_constraint_passed"
    frame[hard_col] = frame.get(hard_col, False).astype(bool)
    scores = pd.to_numeric(frame.get("real_score", frame.get("overall_score", 0.0)), errors="coerce").fillna(0.0)
    feasible_scores = scores.where(frame[hard_col], other=np.nan)
    curve = feasible_scores.cummax().fillna(0.0).tolist()
    target_hits = [idx + 1 for idx, value in enumerate(curve) if value >= target_score]
    feasible_hits = [idx + 1 for idx, passed in enumerate(frame[hard_col].tolist()) if passed]
    return {
        "best_feasible_score_under_budget": float(np.nanmax(feasible_scores)) if not feasible_scores.isna().all() else None,
        "convergence_curve": [float(value) for value in curve],
        "convergence_auc": float(np.trapezoid(curve)) if len(curve) > 1 else float(curve[0]) if curve else 0.0,
        "first_feasible_eval": feasible_hits[0] if feasible_hits else None,
        "fe_at_target": target_hits[0] if target_hits else None,
        "hard_constraint_pass_rate": float(frame[hard_col].mean()),
        "not_evaluable_rate": float((frame.get("status", "") == "not_evaluable").mean()) if "status" in frame.columns else 0.0,
        "simulation_failure_rate": float((frame.get("status", "") == "sim_failed").mean()) if "status" in frame.columns else 0.0,
        "mean_violation": float(
            pd.to_numeric(
                frame["constraint_violation"] if "constraint_violation" in frame.columns else pd.Series(0.0, index=frame.index),
                errors="coerce",
            )
            .fillna(0.0)
            .mean()
        ),
        "candidate_hit_rate": float((scores >= target_score).mean()),
        "l1_discovery_count": int((frame.get("level_label", "") == "L1").sum()) if "level_label" in frame.columns else 0,
        "enrichment_factor": float((scores >= target_score).mean() / max(1 / len(frame), 1e-9)),
    }


def run_ablation_benchmark(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    output_dir: str | Path,
    strategies: Sequence[str] = ("random", "ca_llso_raw_distance", "pia_physics_distance"),
    target_score: float = 80,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    labeled_history = assign_level_labels(history)
    results = []
    curves = []
    for strategy in strategies:
        selected = select_candidates(candidates, labeled_history, strategy=strategy, top_k=top_k, config=config).selected_candidates.copy()
        selected.to_csv(out / f"{strategy}_selected_candidates.csv", index=False)
        selected["real_score"] = pd.to_numeric(selected.get("overall_score", selected.get("predicted_score", 0.0)), errors="coerce").fillna(0.0)
        selected["hard_pass"] = selected.get("hard_constraint_passed", selected.get("p_hard_pass", 0.0)).astype(float) >= 0.5
        selected["status"] = np.where(selected["hard_pass"], "evaluated_feasible", "evaluated_soft_fail")
        metrics = compute_run_metrics(selected, target_score=target_score)
        row = {"method": strategy, **{key: value for key, value in metrics.items() if key != "convergence_curve"}}
        results.append(row)
        for idx, value in enumerate(metrics["convergence_curve"], start=1):
            curves.append({"method": strategy, "eval_index": idx, "best_feasible_score": value})
    result_frame = pd.DataFrame(results)
    result_frame.to_csv(out / "pia_ablation_results.csv", index=False)
    pd.DataFrame(curves).to_csv(out / "pia_convergence_curve.csv", index=False)
    summary = {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "claim_boundary": "external benchmark over evaluated simulation records",
        "methods": list(strategies),
        "target_score": target_score,
        "best_method": None if result_frame.empty else str(result_frame.sort_values("best_feasible_score_under_budget", ascending=False).iloc[0]["method"]),
    }
    (out / "pia_ablation_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "pia_ablation_report.md").write_text(render_benchmark_report(result_frame, summary), encoding="utf-8")
    return summary


def render_benchmark_report(results: pd.DataFrame, summary: dict[str, object]) -> str:
    lines = [
        "# PIA-CA-LLSO Ablation Benchmark",
        "",
        "This report compares next-run candidate selection strategies using externally evaluated simulation records.",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- predicted_score cannot prove final algorithm quality",
        "- attention score cannot prove final algorithm quality",
        "",
        "| Method | Best Feasible ↑ | AUC ↑ | FE@80 ↓ | HPR ↑ | NER ↓ | SFR ↓ | CHR ↑ | L1 Count ↑ | Final Score ↑ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in results.iterrows():
        lines.append(
            f"| {row['method']} | {row.get('best_feasible_score_under_budget', '')} | "
            f"{float(row.get('convergence_auc', 0.0)):.3f} | {row.get('fe_at_target', '')} | "
            f"{float(row.get('hard_constraint_pass_rate', 0.0)):.3f} | {float(row.get('not_evaluable_rate', 0.0)):.3f} | "
            f"{float(row.get('simulation_failure_rate', 0.0)):.3f} | {float(row.get('candidate_hit_rate', 0.0)):.3f} | "
            f"{int(row.get('l1_discovery_count', 0))} | {row.get('best_feasible_score_under_budget', '')} |"
        )
    lines.extend(["", f"Best method in this offline run: {summary.get('best_method')}", ""])
    return "\n".join(lines)


def compute_evolution_metrics(
    evolution_summary: dict[str, Any],
    target_score: float = 80,
) -> dict[str, Any]:
    """Compute closed-loop evolution benchmark metrics from an evolution summary.

    Returns metrics that are separate from single-step strategy metrics,
    with clear labels to avoid unfair comparison.
    """
    return {
        "evolution_generations_run": evolution_summary.get("generations_run", 0),
        "evolution_simulations_used": evolution_summary.get("simulations_used", 0),
        "evolution_best_score": evolution_summary.get("best_score"),
        "evolution_target_reached": evolution_summary.get("target_reached", False),
        "evolution_stop_reason": evolution_summary.get("stop_reason", "unknown"),
        "evolution_budget_to_target": (
            evolution_summary.get("simulations_used")
            if evolution_summary.get("target_reached")
            else None
        ),
        "closed_loop_mode": "evolution",
        "single_step_mode": "not_applicable",
    }


def run_closed_loop_benchmark(
    evolution_dir: str | Path,
    output_dir: str | Path,
    target_score: float = 80,
) -> dict[str, Any]:
    """Compute budget-aware metrics for a completed pia-evolve run."""
    root = Path(evolution_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = root / "evolution_summary.json"
    history_path = root / "evolution_history.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"missing evolution_summary.json: {summary_path}")
    if not history_path.exists():
        raise FileNotFoundError(f"missing evolution_history.csv: {history_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    history = pd.read_csv(history_path)
    scores = pd.to_numeric(history.get("overall_score", pd.Series(dtype=float)), errors="coerce")
    source = history.get("source", pd.Series("", index=history.index)).fillna("")
    initial_scores = scores[source != "simulation_result"].dropna()
    final_scores = scores.dropna()
    best_initial = float(initial_scores.max()) if not initial_scores.empty else None
    best_final = float(final_scores.max()) if not final_scores.empty else summary.get("best_score")
    imported_from_history = int((source == "simulation_result").sum())
    imported_from_summaries = 0

    suggestion_count = 0
    generation_summaries = sorted(root.glob("generation_*/generation_summary.json"))
    if generation_summaries:
        for path in generation_summaries:
            payload = json.loads(path.read_text(encoding="utf-8"))
            suggestion_count += int(payload.get("selected_rows", 0) or 0)
            imported_from_summaries += int(payload.get("imported_result_rows", 0) or 0)
        imported_result_count = max(imported_from_history, imported_from_summaries)
    else:
        imported_result_count = imported_from_history
        for path in sorted(root.glob("generation_*/pia_selected_candidates.csv")):
            suggestion_count += len(pd.read_csv(path))

    target_reached = bool(summary.get("target_reached", False))
    simulations_used = int(summary.get("simulations_used", imported_result_count) or 0)
    best_delta = (
        None
        if best_initial is None or best_final is None
        else float(best_final - best_initial)
    )
    metrics: dict[str, Any] = {
        "best_score_initial": best_initial,
        "best_score_final": best_final,
        "best_score_delta": best_delta,
        "target_reached": target_reached,
        "generations_run": int(summary.get("generations_run", 0) or 0),
        "simulations_used": simulations_used,
        "budget_to_target": simulations_used if target_reached and best_final is not None and best_final >= target_score else None,
        "budget_to_best": simulations_used if best_delta is not None and best_delta > 0 else None,
        "stop_reason": summary.get("stop_reason", "unknown"),
        "imported_result_count": imported_result_count,
        "suggestion_count": suggestion_count,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "closed_loop_mode": "evolution",
    }

    (out / "pia_closed_loop_benchmark.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame([metrics]).to_csv(out / "pia_closed_loop_benchmark.csv", index=False)
    report = [
        "# PIA-CA-LLSO Closed-Loop Benchmark",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- closed-loop metrics count imported simulation results separately from suggestions",
        "",
        f"- best_score_initial: {best_initial}",
        f"- best_score_final: {best_final}",
        f"- best_score_delta: {best_delta}",
        f"- simulations_used: {simulations_used}",
        f"- imported_result_count: {imported_result_count}",
        f"- suggestion_count: {suggestion_count}",
        f"- stop_reason: {metrics['stop_reason']}",
        "",
    ]
    (out / "pia_closed_loop_benchmark.md").write_text("\n".join(report), encoding="utf-8")
    return metrics
