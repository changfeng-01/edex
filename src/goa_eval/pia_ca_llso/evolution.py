"""PIA closed-loop evolution orchestrator.

Coordinates the full evolutionary loop:
history -> labeling -> LLSO offspring -> pia-suggest -> simulation -> append -> repeat
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from goa_eval.pia_ca_llso import DATA_SOURCE, ENGINEERING_VALIDITY
from goa_eval.pia_ca_llso.evolution_state import GenerationState
from goa_eval.pia_ca_llso.labeling import assign_level_labels
from goa_eval.pia_ca_llso.loop import suggest_next_run
from goa_eval.pia_ca_llso.offspring import generate_llso_offspring
from goa_eval.pia_ca_llso.simulation_contract import build_simulation_batch
from goa_eval.pia_ca_llso.simulation_executor import run_simulation_step
from goa_eval.pia_ca_llso.io import ensure_output_dir, write_json, write_csv


def run_evolution_loop(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    config: Mapping[str, Any],
    output_dir: Path,
    strategy: str = "classifier_level_hybrid",
    generations: int | None = None,
    offspring_per_generation: int | None = None,
    top_k: int | None = None,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Run the PIA-CA-LLSO closed-loop evolution.

    Returns a summary dictionary with stop_reason, best_score, generation history, etc.
    """
    evo_cfg = config.get("evolution_loop", {})
    gen_count = generations if generations is not None else evo_cfg.get("generations", 5)
    offspring_count = (
        offspring_per_generation
        if offspring_per_generation is not None
        else evo_cfg.get("offspring_per_generation", 24)
    )
    k = top_k if top_k is not None else evo_cfg.get("top_k", 4)
    target_score = config.get("target_score", 100.0)
    patience = evo_cfg.get("patience_generations", 2)
    min_improvement = evo_cfg.get("min_improvement", 0.01)
    budget = evo_cfg.get("simulation_budget", 20)

    ensure_output_dir(output_dir)

    current_history = history.copy()
    generation_states: list[dict[str, Any]] = []
    best_score: float | None = None
    best_score_overall: float | None = None
    generations_without_improvement = 0
    simulations_used = 0
    stop_reason = "max_generations"

    for gen in range(gen_count):
        gen_dir = output_dir / f"generation_{gen:03d}"
        ensure_output_dir(gen_dir)

        # Check target score
        if "overall_score" in current_history.columns:
            current_best = float(current_history["overall_score"].max())
            if best_score is None or current_best > best_score + min_improvement:
                best_score = current_best
                generations_without_improvement = 0
            else:
                generations_without_improvement += 1

            if best_score_overall is None or current_best > best_score_overall:
                best_score_overall = current_best

            if current_best >= target_score:
                stop_reason = "target_score_reached"
                break

        # Check patience
        if generations_without_improvement >= patience:
            stop_reason = "no_improvement_patience_exhausted"
            break

        # Check budget
        if simulations_used >= budget:
            stop_reason = "simulation_budget_exhausted"
            break

        # Label current history
        labeled_history = assign_level_labels(current_history)

        # Generate LLSO offspring
        offspring = generate_llso_offspring(
            history=labeled_history,
            seed_candidates=candidates,
            config=config,
            generation=gen,
            offspring_count=offspring_count,
            random_seed=random_seed,
        )

        if len(offspring) == 0:
            stop_reason = "no_offspring_generated"
            break

        # Combine seed candidates with offspring
        combined_candidates = pd.concat(
            [candidates.reset_index(drop=True), offspring.reset_index(drop=True)],
            ignore_index=True,
        )
        # Deduplicate columns if any overlap
        combined_candidates = combined_candidates.loc[:, ~combined_candidates.columns.duplicated()].copy()

        # Use existing suggest_next_run for selection
        # (repair candidates are auto-generated inside suggest_next_run)
        result = suggest_next_run(
            history=labeled_history,
            candidates=combined_candidates,
            config=dict(config),
            strategy=strategy,
            top_k=k,
        )

        selected = result.selected_candidates

        if len(selected) == 0:
            stop_reason = "no_offspring_generated"
            break

        # Build simulation batch (wraps already-scheduled candidates)
        batch, manifest = build_simulation_batch(
            selected=selected,
            config=config,
            generation=gen,
        )

        # Write batch to disk
        write_csv(str(gen_dir / "simulation_batch.csv"), batch)
        write_json(str(gen_dir / "simulation_manifest.json"), manifest)

        # Run simulation step
        imported, status = run_simulation_step(
            simulation_batch=batch,
            output_dir=gen_dir,
            config=config,
            generation=gen,
        )

        # Record generation state
        state = GenerationState(
            generation=gen,
            history_rows=len(current_history),
            offspring_rows=len(offspring),
            selected_rows=len(selected),
            imported_result_rows=len(imported),
            best_score=best_score,
            stop_reason=None,
        )
        generation_states.append(state.to_dict())

        # If pending, stop
        if status["status"] == "pending_simulation":
            stop_reason = "pending_simulation_results"
            break

        # Append imported results to history
        if len(imported) > 0:
            current_history = pd.concat(
                [current_history, imported], ignore_index=True
            )
            simulations_used += len(imported)

    # Write generation state log
    if generation_states:
        write_json(str(output_dir / "generation_state.jsonl"), generation_states)

    # Write accumulated history
    write_csv(str(output_dir / "evolution_history.csv"), current_history)

    summary: dict[str, Any] = {
        "stop_reason": stop_reason,
        "generations_run": len(generation_states),
        "simulations_used": simulations_used,
        "best_score": best_score_overall,
        "target_reached": (
            best_score_overall is not None
            and best_score_overall >= target_score
        ),
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "claim_boundary": (
            "pre-simulation suggestions require simulation before claims; "
            "imported results are simulation-only, not physical validation"
        ),
    }

    write_json(str(output_dir / "evolution_summary.json"), summary)
    return summary