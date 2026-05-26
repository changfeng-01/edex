# Closed-Loop Optimizer

CircuitPilot's public optimizer is a conservative next-round candidate generator. It does not run a simulator by itself. It reads evaluated simulation results, proposes the next parameter sets to simulate, and keeps the `simulation_only` boundary explicit.

## Score Differentiation

`score_summary.json` keeps the original score fields and adds:

- `constraint_penalties`: per hard constraint details with `current_value`, `threshold`, `violation_ratio`, `penalty`, and `severity`.
- `hard_failure_penalty`: the summed penalty used by `function_score`.

This keeps failed runs distinguishable. A slight `Max_overlap_ratio` or `Max_ripple` exceedance should rank above a much larger exceedance when the failed constraint names are otherwise the same.

## Candidate Loop

After `evaluate-batch` produces a `leaderboard.csv`, run:

```powershell
python -m goa_eval.cli optimize-loop `
  --leaderboard outputs_batch/leaderboard.csv `
  --param-space examples/sample_params.yaml `
  --output-dir outputs/closed_loop `
  --max-candidates 10
```

Outputs:

- `optimization_leaderboard.csv`: evaluated runs re-ranked with hard-constraint pass state before raw score.
- `next_candidates.csv`: machine-readable next-run parameter proposals.
- `next_candidates.md`: readable companion report.
- `optimization_history.json`: provenance and candidate payloads.

`next_candidates.csv` includes `candidate_id`, `candidate_kind`, `source_run_id`, `changed_parameters`, `parameters_json`, `acquisition_score`, `data_source`, and `engineering_validity`.

The intended workflow is:

```text
evaluate-batch -> optimize-loop -> simulate next_candidates.csv -> evaluate-batch again
```

The loop stays local and deterministic. It proposes one-parameter neighbors first, then two-parameter combinations around the current best evaluated run.
