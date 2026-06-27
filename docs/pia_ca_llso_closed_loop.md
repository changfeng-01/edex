# PIA-CA-LLSO Closed-Loop Evolution

> **Evidence Boundary:** All results are simulation-only. They do not constitute physical validation, silicon validation, lab validation, or tapeout validation.
>
> - `data_source = real_simulation_csv`
> - `engineering_validity = simulation_only`

## Overview

The PIA-CA-LLSO closed-loop evolution extends the single-step `pia-suggest` selector into a multi-generation evolutionary optimizer. It generates LLSO (Level-based Learning Search Optimization) offspring, selects simulation batches, runs or imports simulation evidence, appends verified results to history, and repeats until budget or convergence.

## Architecture

```
history
-> level labeling
-> LLSO offspring generation
-> existing pia-suggest selector
-> simulation batch contract
-> simulator execution or result import
-> append verified simulation result rows to history
-> retrain/adapt
-> next generation
```

The outer loop reuses the existing `suggest_next_run()` pipeline as the per-generation selection engine. It does not duplicate selector logic.

## Modes

### Offline Mode (`--mode offline`)

Writes the next simulation batch and stops. Use this when a simulator is not available or when you want to inspect the batch before running simulations manually.

```bash
python -m goa_eval.cli pia-evolve \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy classifier_level_hybrid \
  --generations 2 \
  --offspring-per-generation 8 \
  --top-k 4 \
  --mode offline \
  --output-dir outputs/pia_evolve_offline
```

### Import Results Mode (`--mode import_results`)

Reads result CSV files from the generation directory, validates required fields, appends results to history, and continues to the next generation.

```bash
python -m goa_eval.cli pia-evolve \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy classifier_level_hybrid \
  --generations 2 \
  --offspring-per-generation 8 \
  --top-k 4 \
  --mode import_results \
  --simulation-results-dir results/ \
  --output-dir outputs/pia_evolve_import
```

### External Command Mode (`--mode external_command`)

Calls a configured external simulator via subprocess. Fails closed on command failure, missing result files, or malformed result CSVs. No mock pass is allowed.

```bash
python -m goa_eval.cli pia-evolve \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --mode external_command \
  --external-command "my_simulator --input {candidate_csv} --output {result_csv}" \
  --output-dir outputs/pia_evolve_external
```

Command template variables: `{candidate_csv}`, `{result_csv}`, `{candidate_id}`, `{generation}`, `{output_dir}`.

## Required Result CSV Fields

When importing simulation results, the result CSV must contain:

- `candidate_id`
- `overall_score`
- `hard_constraint_passed`

Additional columns are carried through but not required.

## Generation Artifacts

Each generation writes:

- `generation_XXX/offspring_candidates.csv`
- `generation_XXX/pia_selected_candidates.csv`
- `generation_XXX/simulation_batch.csv`
- `generation_XXX/simulation_manifest.json`
- `generation_XXX/imported_results.csv`
- `generation_XXX/generation_summary.json`

Global outputs:

- `evolution_history.csv` — accumulated evaluated rows across generations
- `generation_state.jsonl` — one JSON object per generation
- `evolution_summary.json` — final stop reason, best score, generation count
- `evolution_report.md` — markdown summary report

## Stop Reasons

| Reason | Description |
|--------|-------------|
| `target_score_reached` | Best score meets or exceeds target |
| `max_generations` | Maximum generations reached |
| `simulation_budget_exhausted` | Simulation budget limit reached |
| `no_improvement_patience_exhausted` | No improvement for configured patience generations |
| `pending_simulation_results` | Offline mode — batch written, awaiting simulation |
| `no_offspring_generated` | LLSO could not generate offspring |

## LLSO Offspring Generation

LLSO generates offspring using level-based teacher-learner optimization:

```
child = learner + r1 * (teacher - learner) + r2 * (elite - learner) + noise
```

- Teachers and elites are sampled from L1 (best) history rows
- Learners are sampled from L2/L3 (weaker) rows
- Parameters are clamped to inferred bounds
- Duplicate parameter vectors are deduplicated
- Falls back to best available rows when L1 is missing

## Claim Boundary

**Every pre-simulation suggestion has `must_resimulate = true`.**

**Every imported simulator result keeps `data_source = real_simulation_csv` and `engineering_validity = simulation_only`.**

PIA never claims physical validation, silicon validation, lab validation, tapeout validation, or measured hardware validation. Do not use paper-derived values or weak labels as reproduced simulation evidence.

## CLI Reference

```
python -m goa_eval.cli pia-evolve --help
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--history-csv` | Yes | — | Path to simulation history CSV |
| `--candidate-csv` | Yes | — | Path to seed candidate CSV |
| `--config` | Yes | — | Path to YAML config file |
| `--output-dir` | Yes | — | Output directory for all artifacts |
| `--strategy` | No | `classifier_level_hybrid` | Selection strategy |
| `--generations` | No | From config | Max generations |
| `--offspring-per-generation` | No | From config | Offspring count per generation |
| `--top-k` | No | From config | Candidates selected per generation |
| `--mode` | No | `offline` | Simulation mode |
| `--simulation-results-dir` | No | — | Directory with result CSVs (import mode) |
| `--external-command` | No | — | Shell command template (external mode) |
| `--target-score` | No | From config | Target score for early stopping |
| `--seed` | No | `42` | Random seed |
