# PIA-CA-LLSO API

## Standard History CSV

Recommended columns:

- `sample_id`
- parameter columns
- `overall_score`
- `hard_constraint_passed`
- `sim_success`
- `status`
- `source`

Rows with `status = predicted_only` are excluded from external benchmark evidence.

## Standard Candidate CSV

Recommended columns:

- `candidate_id`
- parameter columns
- optional `p_l1`
- optional `p_hard_pass`
- optional `predicted_score`
- optional `uncertainty`
- `source`

## Selected Candidate CSV

`pia_selected_candidates.csv` includes:

- `selected_rank`
- `candidate_role`
- `selection_reason`
- `acquisition_score`
- `acquisition_components_json`
- `diagnostic_status`

When `--strategy pia_capm_distance` is used, the selected candidate CSV also includes:

- `capm_distance_to_l1`
- `capm_geodesic_distance_to_l1`
- `capm_barrier_score`
- `capm_missing_penalty`
- `capm_hard_risk_passed`

These fields are pre-simulation candidate-selection diagnostics. They are not final physical validation evidence, and every selected candidate keeps `must_resimulate = true`.

## Adapter Interface

`HistoryAdapter` and `CandidateAdapter` are CSV-first adapters. Future integration can map existing optimize-rounds or strategy outputs into these DataFrames.

## CLI Commands

- `pia-label`
- `pia-suggest`
- `pia-benchmark`
- `pia-export-contract`
- `pia-train-from-db`
- `pia-evolve` — Run multi-generation closed-loop evolution

## pia-evolve Output

| Artifact | Description |
|----------|-------------|
| `evolution_history.csv` | Accumulated evaluated rows across generations |
| `generation_state.jsonl` | One JSON object per generation |
| `evolution_summary.json` | Final stop reason, best score, generation count |
| `evolution_report.md` | Markdown summary report |
| `generation_XXX/simulation_batch.csv` | Candidates for simulation this generation |
| `generation_XXX/simulation_manifest.json` | Boundary labels and candidate count |
