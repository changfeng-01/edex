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
from goa_eval.pia_ca_llso.io import ensure_output_dir, write_csv, write_json, write_jsonl, write_markdown
from goa_eval.pia_ca_llso.report import render_evolution_report


def load_resume_state(output_dir: str | Path, generation: int) -> dict[str, Any]:
    """Load accumulated history and pending simulation batch for resume."""
    root = Path(output_dir)
    history_path = root / "evolution_history.csv"
    batch_path = root / f"generation_{generation:03d}" / "simulation_batch.csv"
    if not history_path.exists():
        raise FileNotFoundError(f"missing evolution_history.csv in {root}")
    if not batch_path.exists():
        raise FileNotFoundError(f"missing pending simulation_batch.csv: {batch_path}")
    return {
        "history": pd.read_csv(history_path),
        "simulation_batch": pd.read_csv(batch_path),
        "generation": generation,
        "next_generation": generation + 1,
    }


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
    resume_from: str | Path | None = None,
    resume_generation: int | None = None,
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
    if "data_source" not in current_history.columns:
        current_history["data_source"] = DATA_SOURCE
    if "engineering_validity" not in current_history.columns:
        current_history["engineering_validity"] = ENGINEERING_VALIDITY
    generation_states: list[dict[str, Any]] = []
    generation_artifacts: list[str] = []
    best_score: float | None = None
    best_score_overall: float | None = None
    generations_without_improvement = 0
    simulations_used = 0
    stop_reason = "max_generations"
    start_generation = 0

    if resume_from is not None:
        if resume_generation is None:
            raise ValueError("resume_generation is required when resume_from is set")
        resume_state = load_resume_state(resume_from, resume_generation)
        current_history = resume_state["history"]
        if "data_source" not in current_history.columns:
            current_history["data_source"] = DATA_SOURCE
        if "engineering_validity" not in current_history.columns:
            current_history["engineering_validity"] = ENGINEERING_VALIDITY
        resume_batch = resume_state["simulation_batch"]
        resume_dir = Path(resume_from) / f"generation_{resume_generation:03d}"
        imported, status = run_simulation_step(
            simulation_batch=resume_batch,
            output_dir=resume_dir,
            config=config,
            generation=resume_generation,
        )
        if len(imported) == 0:
            raise ValueError(
                "resume result import produced no rows; check candidate_id values "
                "and required result columns"
            )
        imported_path = resume_dir / "imported_results.csv"
        write_csv(str(imported_path), imported)
        current_history = pd.concat([current_history, imported], ignore_index=True)
        simulations_used += len(imported)
        start_generation = int(resume_state["next_generation"])
        generation_states.append(
            GenerationState(
                generation=resume_generation,
                history_rows=len(current_history),
                offspring_rows=0,
                selected_rows=len(resume_batch),
                imported_result_rows=len(imported),
                best_score=None,
                stop_reason="resumed_results_imported",
                must_resimulate=False,
            ).to_dict()
        )
        summary_path = resume_dir / "generation_summary.json"
        write_json(str(summary_path), {
            "generation": resume_generation,
            "status": status,
            "imported_result_rows": len(imported),
            "resume_from": str(Path(resume_from)),
            "data_source": DATA_SOURCE,
            "engineering_validity": ENGINEERING_VALIDITY,
        })

    for gen in range(start_generation, gen_count):
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
        offspring_path = gen_dir / "offspring_candidates.csv"
        write_csv(str(offspring_path), offspring)
        generation_artifacts.append(str(offspring_path.relative_to(output_dir)))

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
        selected["must_resimulate"] = True
        selected["data_source"] = DATA_SOURCE
        selected["engineering_validity"] = ENGINEERING_VALIDITY
        selected_path = gen_dir / "pia_selected_candidates.csv"
        write_csv(str(selected_path), selected)
        generation_artifacts.append(str(selected_path.relative_to(output_dir)))

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
        batch_path = gen_dir / "simulation_batch.csv"
        manifest_path = gen_dir / "simulation_manifest.json"
        write_csv(str(batch_path), batch)
        write_json(str(manifest_path), manifest)
        generation_artifacts.extend([
            str(batch_path.relative_to(output_dir)),
            str(manifest_path.relative_to(output_dir)),
        ])

        # Run simulation step
        imported, status = run_simulation_step(
            simulation_batch=batch,
            output_dir=gen_dir,
            config=config,
            generation=gen,
        )
        imported_path = gen_dir / "imported_results.csv"
        if len(imported) > 0:
            write_csv(str(imported_path), imported)
        else:
            result_cols = config.get("simulation_executor", {}).get(
                "result_required_columns",
                ["candidate_id", "overall_score", "hard_constraint_passed"],
            )
            empty_cols = list(dict.fromkeys([*result_cols, *batch.columns]))
            write_csv(str(imported_path), pd.DataFrame(columns=empty_cols))
        generation_artifacts.append(str(imported_path.relative_to(output_dir)))

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
        generation_summary = {
            **state.to_dict(),
            "status": status,
            "artifacts": [
                str((gen_dir / "offspring_candidates.csv").relative_to(output_dir)),
                str((gen_dir / "pia_selected_candidates.csv").relative_to(output_dir)),
                str((gen_dir / "simulation_batch.csv").relative_to(output_dir)),
                str((gen_dir / "simulation_manifest.json").relative_to(output_dir)),
                str(imported_path.relative_to(output_dir)),
            ],
            "data_source": DATA_SOURCE,
            "engineering_validity": ENGINEERING_VALIDITY,
        }
        summary_path = gen_dir / "generation_summary.json"
        write_json(str(summary_path), generation_summary)
        generation_artifacts.append(str(summary_path.relative_to(output_dir)))

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
        write_jsonl(str(output_dir / "generation_state.jsonl"), generation_states)

    # Write accumulated history
    write_csv(str(output_dir / "evolution_history.csv"), current_history)
    if "overall_score" in current_history.columns:
        score_series = pd.to_numeric(current_history["overall_score"], errors="coerce").dropna()
        if not score_series.empty:
            best_score_overall = float(score_series.max())

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
        "latest_simulation_batch": (
            next((artifact for artifact in reversed(generation_artifacts) if artifact.endswith("simulation_batch.csv")), None)
        ),
        "generation_artifacts": generation_artifacts,
    }

    write_json(str(output_dir / "evolution_summary.json"), summary)
    write_markdown(str(output_dir / "evolution_report.md"), render_evolution_report(summary))
    return summary
