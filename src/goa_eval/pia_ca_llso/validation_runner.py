"""Single-run executor for PIA-CA-LLSO validation experiments."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from goa_eval.pia_ca_llso import DATA_SOURCE, ENGINEERING_VALIDITY
from goa_eval.pia_ca_llso.ablation import build_ablation_config
from goa_eval.pia_ca_llso.boundary_audit import audit_evolution_outputs
from goa_eval.pia_ca_llso.evolution import run_evolution_loop
from goa_eval.pia_ca_llso.io import write_json
from goa_eval.pia_ca_llso.validation_protocol import ValidationRunSpec


def run_validation_spec(
    spec: ValidationRunSpec,
    scenario_bundle: dict,
    output_root: Path,
    smoke: bool = False,
) -> dict[str, Any]:
    run_dir = _run_dir(output_root, spec)
    run_dir.mkdir(parents=True, exist_ok=True)
    config, ablation_strategy = build_ablation_config(dict(scenario_bundle["config"]), spec.ablation)
    strategy = ablation_strategy if spec.method == "pia_evolve_full" else spec.method
    _prepare_config(config, spec, scenario_bundle, smoke)

    manifest = {
        "scenario_id": spec.scenario_id,
        "method": spec.method,
        "ablation": spec.ablation,
        "strategy": strategy,
        "seed": spec.seed,
        "budget": spec.budget,
        "target_score": spec.target_score,
        "history_csv": scenario_bundle["history_csv"],
        "candidate_csv": scenario_bundle["candidate_csv"],
        "source_type": scenario_bundle["source_type"],
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": True,
        "claim_boundary": scenario_bundle["claim_boundary"],
    }
    write_json(run_dir / "run_manifest.json", manifest)

    evolution_summary = run_evolution_loop(
        history=scenario_bundle["history"].copy(),
        candidates=scenario_bundle["candidates"].copy(),
        config=config,
        output_dir=run_dir,
        strategy=strategy,
        generations=config["evolution_loop"]["generations"],
        offspring_per_generation=config["evolution_loop"]["offspring_per_generation"],
        top_k=config["evolution_loop"]["top_k"],
        random_seed=spec.seed,
    )
    audit = audit_evolution_outputs(run_dir)
    write_json(run_dir / "boundary_audit.json", audit)

    summary = {
        **manifest,
        **_compute_run_metrics(run_dir, scenario_bundle["history"], evolution_summary, spec),
        "boundary_audit_passed": bool(audit.get("passed", False)),
        "boundary_issue_count": len(audit.get("issues", [])),
        "run_path": str(run_dir.relative_to(output_root)),
    }
    write_json(run_dir / "run_summary.json", summary)
    return summary


def _prepare_config(config: dict, spec: ValidationRunSpec, scenario_bundle: dict, smoke: bool) -> None:
    config["target_score"] = spec.target_score
    config.setdefault("simulation_executor", {})["mode"] = (
        "local_fixture" if smoke or scenario_bundle["source_type"] == "local_fixture" else "offline"
    )
    top_k = min(4, max(1, int(spec.budget)))
    generations = max(1, int(math.ceil(spec.budget / top_k)))
    loop = config.setdefault("evolution_loop", {})
    loop["simulation_budget"] = int(spec.budget)
    loop["top_k"] = top_k
    loop["generations"] = generations
    loop.setdefault("patience_generations", generations + 1)
    loop.setdefault("min_improvement", 0.0)
    loop.setdefault("offspring_per_generation", 8)
    config.setdefault(
        "simulation_executor",
        {},
    ).setdefault("result_required_columns", ["candidate_id", "overall_score", "hard_constraint_passed"])


def _compute_run_metrics(
    run_dir: Path,
    initial_history: pd.DataFrame,
    evolution_summary: dict[str, Any],
    spec: ValidationRunSpec,
) -> dict[str, Any]:
    history_path = run_dir / "evolution_history.csv"
    history = pd.read_csv(history_path) if history_path.exists() else initial_history.copy()
    imported = history[history.get("source", pd.Series(dtype="object")).fillna("") == "simulation_result"].copy()
    imported_scores = pd.to_numeric(imported.get("overall_score", pd.Series(dtype="float64")), errors="coerce")
    initial_scores = pd.to_numeric(initial_history.get("overall_score", pd.Series(dtype="float64")), errors="coerce")
    best_score_final = evolution_summary.get("best_score")
    if best_score_final is None and not imported_scores.dropna().empty:
        best_score_final = float(imported_scores.max())
    initial_best = float(initial_scores.max()) if not initial_scores.dropna().empty else 0.0
    target_hits = imported_scores >= float(spec.target_score)
    simulations_to_target = int(target_hits[target_hits].index[0] - imported.index[0] + 1) if target_hits.any() else None
    cumulative_best = imported_scores.cummax().dropna()
    hard_pass_rate = _mean_bool(imported.get("hard_constraint_passed", pd.Series(dtype="object")))
    return {
        "simulations_used": int(evolution_summary.get("simulations_used", len(imported))),
        "target_hit": bool(evolution_summary.get("target_reached", False) or target_hits.any()),
        "simulations_to_target": simulations_to_target,
        "best_score_final": best_score_final,
        "best_score_delta": (float(best_score_final) - initial_best) if best_score_final is not None else None,
        "convergence_auc": float(cumulative_best.mean()) if not cumulative_best.empty else None,
        "hard_pass_rate": hard_pass_rate,
        "mean_constraint_violation": None if hard_pass_rate is None else 1.0 - hard_pass_rate,
        "invalid_result_rejection_count": 0,
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": True,
    }


def _mean_bool(series: pd.Series) -> float | None:
    if series.empty:
        return None
    values = series.map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    return float(values.mean())


def _run_dir(output_root: Path, spec: ValidationRunSpec) -> Path:
    return (
        output_root
        / f"scenario={spec.scenario_id}"
        / f"method={spec.method}"
        / f"ablation={spec.ablation}"
        / f"budget={spec.budget}"
        / f"seed={spec.seed}"
    )
