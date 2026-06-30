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
from goa_eval.pia_ca_llso.formal_audit import file_sha256, object_sha256
from goa_eval.pia_ca_llso.io import write_json
from goa_eval.pia_ca_llso.leakage import assert_no_result_leakage
from goa_eval.pia_ca_llso.validation_protocol import ValidationRunSpec


def run_validation_spec(
    spec: ValidationRunSpec,
    scenario_bundle: dict,
    output_root: Path,
    smoke: bool = False,
) -> dict[str, Any]:
    run_dir = _run_dir(output_root, spec)
    run_dir.mkdir(parents=True, exist_ok=True)
    assert_no_result_leakage(scenario_bundle["candidates"], f"scenario {spec.scenario_id} candidate pool")
    config, ablation_strategy = build_ablation_config(dict(scenario_bundle["config"]), spec.ablation)
    strategy = ablation_strategy if spec.method in {"classifier_level_hybrid", "pia_evolve_full"} and spec.ablation != "full" else spec.method
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
        "history_hash": file_sha256(scenario_bundle["history_csv"]),
        "candidate_pool_hash": file_sha256(scenario_bundle["candidate_csv"]),
        "scoring_config_hash": object_sha256(config),
        "leakage_check_passed": True,
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
        "result_source": "best_so_far_curve.csv",
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
    initial_scores = pd.to_numeric(initial_history.get("overall_score", pd.Series(dtype="float64")), errors="coerce")
    curve = _write_best_so_far_curve(run_dir, imported, spec)
    metrics = _metrics_from_curve(curve, spec.target_score)
    initial_best = float(initial_scores.max()) if not initial_scores.dropna().empty else 0.0
    hard_pass_rate = _mean_bool(imported.get("hard_constraint_passed", pd.Series(dtype="object")))
    best_score_final = metrics["best_score_final"]
    return {
        "simulations_used": int(evolution_summary.get("simulations_used", len(imported))),
        "target_hit": metrics["target_hit"],
        "simulations_to_target": metrics["simulations_to_target"],
        "best_score_final": best_score_final,
        "best_score_delta": (float(best_score_final) - initial_best) if best_score_final is not None else None,
        "convergence_auc": metrics["convergence_auc"],
        "hard_pass_rate": hard_pass_rate,
        "mean_constraint_violation": None if hard_pass_rate is None else 1.0 - hard_pass_rate,
        "invalid_result_rejection_count": 0,
        "evidence_status": metrics["evidence_status"],
        "best_so_far_curve_path": str(run_dir / "best_so_far_curve.csv"),
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": True,
    }


def _metrics_from_curve(curve: pd.DataFrame, target_score: float) -> dict[str, Any]:
    if curve.empty or "best_feasible_score" not in curve.columns:
        return {
            "target_hit": False,
            "simulations_to_target": None,
            "best_score_final": None,
            "convergence_auc": None,
            "evidence_status": "not_evaluable",
        }
    best = pd.to_numeric(curve["best_feasible_score"], errors="coerce").dropna()
    if best.empty:
        return {
            "target_hit": False,
            "simulations_to_target": None,
            "best_score_final": None,
            "convergence_auc": None,
            "evidence_status": "not_evaluable",
        }
    hits = curve["target_hit_so_far"].astype(bool) if "target_hit_so_far" in curve.columns else best >= float(target_score)
    hit_indices = list(hits[hits].index)
    return {
        "target_hit": bool(hit_indices),
        "simulations_to_target": int(curve.loc[hit_indices[0], "budget_index"]) if hit_indices else None,
        "best_score_final": float(best.iloc[-1]),
        "convergence_auc": float(best.mean()),
        "evidence_status": "evaluable",
    }


def _mean_bool(series: pd.Series) -> float | None:
    if series.empty:
        return None
    values = series.map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    return float(values.mean())


def _write_best_so_far_curve(run_dir: Path, imported: pd.DataFrame, spec: ValidationRunSpec) -> pd.DataFrame:
    scores = pd.to_numeric(imported.get("overall_score", pd.Series(dtype="float64")), errors="coerce").reset_index(drop=True)
    hard = _bool_series(imported.get("hard_constraint_passed", pd.Series(dtype="object"))).reset_index(drop=True)
    feasible_scores = scores.where(hard)
    best = feasible_scores.cummax()
    curve = pd.DataFrame(
        {
            "budget_index": range(1, len(scores) + 1),
            "candidate_id": imported.get("candidate_id", pd.Series(dtype="object")).astype(str).reset_index(drop=True),
            "overall_score": scores,
            "best_feasible_score": best,
            "target_hit_so_far": best.ge(float(spec.target_score)).fillna(False).astype(bool),
            "hard_constraint_passed": hard,
            "data_source": DATA_SOURCE,
            "engineering_validity": ENGINEERING_VALIDITY,
            "must_resimulate": True,
        }
    )
    curve.to_csv(run_dir / "best_so_far_curve.csv", index=False)
    return curve


def _bool_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=bool)
    return series.map(lambda value: str(value).strip().lower() in {"true", "1", "yes"}).astype(bool)


def _run_dir(output_root: Path, spec: ValidationRunSpec) -> Path:
    return (
        output_root
        / f"scenario={spec.scenario_id}"
        / f"method={spec.method}"
        / f"ablation={spec.ablation}"
        / f"budget={spec.budget}"
        / f"seed={spec.seed}"
    )
