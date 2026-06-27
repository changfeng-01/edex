# PIA-CA-LLSO Closed Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full PIA-CA-LLSO evolutionary closed loop that generates LLSO offspring, selects simulation batches, runs or imports simulation evidence, appends verified results to history, retrains models, and repeats until budget or convergence.

**Architecture:** Keep the current `pia-suggest` stack as the single-generation selection engine. Add a thin evolution layer around it: generation state, LLSO offspring generation, simulation batch contracts, simulation result import/execution, history append, and convergence checks. Preserve the evidence boundary: pre-simulation rows are next-run suggestions with `must_resimulate = true`; imported simulator results remain `engineering_validity = simulation_only`, not physical validation.

**Tech Stack:** Python, pandas, numpy, argparse CLI, existing `goa_eval.pia_ca_llso` modules, existing pytest suite, optional external simulator command integration through subprocess.

---

## Context for DeepSeek

This plan is for the repository at `D:\EDA大赛`. The implementation should be additive inside the existing `goa_eval` package. Do not create a parallel project, do not remove existing CLI commands, and do not rename existing evidence fields.

Current mainline already includes these PIA-CA-LLSO capabilities:

- `pia-label`: labels simulation history into levels.
- `pia-suggest`: emits next-run candidate suggestions.
- `pia-benchmark`: compares single-step PIA selection strategies.
- `pia-export-contract`: writes the current API contract.
- `pia-train-from-db`: builds PIA training data from existing paper/database artifacts.
- `pia_capm_distance`: fixed CAPM physics-distance baseline.
- `adaptive_pia_capm`: learns CAPM feature/acquisition weights from history when enough rows exist.
- `classifier_level_hybrid`: uses classifier predictions plus CAPM/diversity for ranking.
- constraint-ledger repair candidates are already merged into `pia-suggest`.
- evaluation scheduler already attaches `evaluation_state`, `simulation_window`, `constraint_eval_plan_json`, `evidence_state`, and `must_resimulate` to selected rows.

The missing piece is not another one-step ranking strategy. The missing piece is the outer evolutionary closed loop:

```text
history
-> level labeling
-> LLSO offspring generation
-> existing pia-suggest selector
-> simulation batch
-> simulator execution or result import
-> append verified simulation result rows to history
-> retrain/adapt
-> next generation
```

Important existing files:

- `src/goa_eval/cli_commands/pia_ca_llso.py`: register new CLI command here.
- `src/goa_eval/pia_ca_llso/loop.py`: existing single-generation `suggest_next_run()` pipeline.
- `src/goa_eval/pia_ca_llso/selector.py`: existing ranking strategies.
- `src/goa_eval/pia_ca_llso/candidate_generator.py`: existing constraint-ledger repair candidate generation.
- `src/goa_eval/pia_ca_llso/evaluation_scheduler.py`: existing simulation-window scheduling metadata.
- `src/goa_eval/pia_ca_llso/sklearn_baseline.py`: classifier training/prediction helpers.
- `src/goa_eval/pia_ca_llso/physics_distance.py`: CAPM physics feature distance and barrier logic.
- `src/goa_eval/pia_ca_llso/labeling.py`: existing L1/L2/L3 label assignment.
- `src/goa_eval/pia_ca_llso/io.py`: config and artifact IO helpers.
- `config/pia_ca_llso_goa_profile.yaml`: GOA-specific PIA config.
- `config/pia_ca_llso_default.yaml`: default PIA config.
- `examples/pia_ca_llso/sample_history.csv`: small sample history.
- `examples/pia_ca_llso/sample_candidates.csv`: small sample candidate pool.

Current verified baseline before this plan:

```bash
python -m pytest tests -k pia -q
```

Expected baseline:

```text
45 passed, 307 deselected, 1 warning
```

Known CLI smoke command for the current classifier hybrid strategy:

```bash
python -m goa_eval.cli pia-suggest \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy classifier_level_hybrid \
  --top-k 4 \
  --output-dir outputs/pia_suggest_classifier_hybrid_main
```

DeepSeek should preserve these boundary labels exactly:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Meaning:

- Before simulation, candidates are only next-run suggestions. They must keep `must_resimulate = true`.
- After simulation result import, rows can become evaluated simulation evidence, but still only `engineering_validity = simulation_only`.
- Never claim physical validation, silicon validation, lab validation, tapeout validation, or measured hardware validation.
- Do not use paper-derived values or weak labels as reproduced simulation evidence.

Implementation constraints:

- Use TDD. For each task, add the failing test first, run it, implement the smallest compatible code, then rerun the focused test.
- Keep this additive. Reuse `suggest_next_run()` instead of duplicating selector logic.
- Do not introduce new external dependencies unless there is no standard-library or existing-dependency solution.
- Keep `.trae/` untouched if it appears in the working tree.
- Generated outputs under `outputs/` should not be committed unless a test fixture explicitly needs a small deterministic file.
- If a simulator is unavailable, `offline` and `import_results` modes must still work.
- External simulator mode must fail closed on command failure, missing result files, or malformed result CSVs.

Recommended implementation order:

1. Schema and state: `evolution_state.py`.
2. LLSO generation: `offspring.py`.
3. Simulation batch/result contract: `simulation_contract.py`.
4. Offline/import/external executor: `simulation_executor.py`.
5. Closed-loop orchestrator: `evolution.py`.
6. CLI integration: add `pia-evolve`.
7. Reports/docs/benchmark support.

Recommended DeepSeek working prompt:

```text
You are working in D:\EDA大赛. Implement docs/plans/2026-06-26-pia-ca-llso-closed-loop.md task by task using TDD. Preserve existing pia-label, pia-suggest, pia-benchmark, pia-export-contract, and pia-train-from-db behavior. Reuse suggest_next_run() for per-generation selection. Preserve data_source = real_simulation_csv, engineering_validity = simulation_only, and must_resimulate = true exactly in pre-simulation artifacts. Do not touch .trae/. Stop and report if tests reveal unrelated failures or if external simulator integration cannot be validated locally.
```

---

## Target User Flow

Command:

```bash
python -m goa_eval.cli pia-evolve \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy classifier_level_hybrid \
  --generations 5 \
  --offspring-per-generation 24 \
  --top-k 4 \
  --mode offline \
  --output-dir outputs/pia_evolve_closed_loop
```

Offline mode writes the next simulation batch and stops each generation if no result file is available. Closed-loop mode either imports result CSV files or calls a configured external simulator command, then appends the parsed results and continues.

Artifacts:

- `evolution_history.csv`: accumulated evaluated rows across generations.
- `generation_state.jsonl`: one JSON object per generation.
- `generation_000/offspring_candidates.csv`
- `generation_000/pia_selected_candidates.csv`
- `generation_000/simulation_batch.csv`
- `generation_000/simulation_manifest.json`
- `generation_000/imported_results.csv`
- `generation_000/generation_summary.json`
- `evolution_report.md`

---

## Closed-Loop Algorithm

For each generation:

1. Load current evaluated history.
2. Assign L1/L2/L3 labels with existing `assign_level_labels()`.
3. Infer parameter bounds from config and observed numeric parameter values.
4. Generate LLSO offspring:
   - sample weak learners from L2/L3;
   - sample teachers from L1;
   - generate child parameters with level-based learning;
   - add small mutation noise;
   - clamp to safe inferred bounds;
   - deduplicate by parameter vector.
5. Merge offspring with seed candidates and existing constraint-ledger repair candidates through `suggest_next_run()`.
6. Rank with `classifier_level_hybrid` by default.
7. Attach evaluation scheduling and emit a simulation batch.
8. If `mode = offline`, stop after writing pending batch.
9. If `mode = import_results`, read result CSV for selected candidates, validate required fields, append to history, and continue.
10. If `mode = external_command`, render one candidate input per selected row, call the configured simulator command, parse result CSV/JSON, append to history, and continue.
11. Stop when target score is reached, simulation budget is exhausted, max generations is reached, or no improvement patience is exceeded.

Important boundary:

- Candidate suggestions: `must_resimulate = true`, `evidence_state = pending_simulation`.
- Imported/executed simulator rows: `data_source = real_simulation_csv`, `engineering_validity = simulation_only`.
- No row should claim silicon, lab, tapeout, or physical validation.

---

## Config Additions

Modify:

- `config/pia_ca_llso_goa_profile.yaml`
- `config/pia_ca_llso_default.yaml`

Add:

```yaml
evolution_loop:
  enabled: true
  level_strategy: labeled_history
  generations: 5
  offspring_per_generation: 24
  top_k: 4
  target_score: 80
  patience_generations: 2
  min_improvement: 0.01
  simulation_budget: 20
  random_seed: 42

llso_offspring:
  enabled: true
  teacher_level: L1
  learner_levels: [L2, L3]
  teacher_fraction: 0.5
  elite_fraction: 0.25
  mutation_fraction: 0.05
  min_history_rows: 4
  dedupe_decimal_places: 6
  max_attempt_multiplier: 5

simulation_executor:
  mode: offline
  result_required_columns:
    - candidate_id
    - overall_score
    - hard_constraint_passed
  external_command: null
  result_glob: "*.csv"
```

---

## Task 1: Generation State Schema

**Files:**

- Create: `src/goa_eval/pia_ca_llso/evolution_state.py`
- Test: `tests/test_pia_evolution_state.py`

**Step 1: Write failing tests**

Test behavior:

- generation state records generation number, parent history size, offspring count, selected count, imported result count, best score, stop reason.
- state can be serialized to JSONL-safe dicts.
- evidence labels remain conservative.

Example test shape:

```python
from goa_eval.pia_ca_llso.evolution_state import GenerationState


def test_generation_state_serializes_boundary_fields() -> None:
    state = GenerationState(
        generation=1,
        history_rows=10,
        offspring_rows=24,
        selected_rows=4,
        imported_result_rows=4,
        best_score=82.5,
        stop_reason=None,
    )

    payload = state.to_dict()

    assert payload["generation"] == 1
    assert payload["data_source"] == "real_simulation_csv"
    assert payload["engineering_validity"] == "simulation_only"
    assert payload["must_resimulate"] is True
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_pia_evolution_state.py -q
```

Expected: FAIL because `evolution_state.py` does not exist.

**Step 3: Implement minimal schema**

Implement a dataclass:

```python
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class GenerationState:
    generation: int
    history_rows: int
    offspring_rows: int
    selected_rows: int
    imported_result_rows: int
    best_score: float | None = None
    stop_reason: str | None = None
    data_source: str = "real_simulation_csv"
    engineering_validity: str = "simulation_only"
    must_resimulate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

**Step 4: Run test**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/evolution_state.py tests/test_pia_evolution_state.py
git commit -m "feat: add PIA evolution state schema"
```

---

## Task 2: LLSO Offspring Generator

**Files:**

- Create: `src/goa_eval/pia_ca_llso/offspring.py`
- Test: `tests/test_pia_llso_offspring.py`

**Step 1: Write failing tests**

Required tests:

- `test_llso_offspring_generates_children_from_lower_levels_toward_l1`
- `test_llso_offspring_clamps_to_inferred_bounds`
- `test_llso_offspring_deduplicates_parameter_vectors`
- `test_llso_offspring_falls_back_to_candidate_sampling_when_l1_missing`

Core assertions:

- output has `candidate_id`, `generation`, `source = llso_offspring`, `parent_candidate_id`, `teacher_sample_id`;
- all configured parameter columns exist;
- values remain within inferred bounds;
- output rows keep `must_resimulate = true` and `engineering_validity = simulation_only`.

**Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_pia_llso_offspring.py -q
```

Expected: FAIL because `offspring.py` does not exist.

**Step 3: Implement bounds and offspring generation**

Public API:

```python
def infer_parameter_bounds(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    parameter_columns: list[str],
) -> dict[str, tuple[float, float]]:
    ...


def generate_llso_offspring(
    history: pd.DataFrame,
    seed_candidates: pd.DataFrame,
    config: dict,
    generation: int,
    offspring_count: int,
    random_seed: int = 42,
) -> pd.DataFrame:
    ...
```

Generation formula:

```text
child = learner
      + r1 * (teacher - learner)
      + r2 * (elite - learner)
      + gaussian_noise
```

Rules:

- `learner` comes from L2/L3 where available.
- `teacher` and `elite` come from L1 where available.
- fallback teacher pool is top score hard-pass rows; final fallback is best available rows.
- noise scale is `(upper - lower) * mutation_fraction`.
- clamp every parameter to inferred bounds.
- skip parameter columns without numeric finite bounds.
- generate at most `offspring_count`; if attempts are exhausted, return fewer rows with reportable status.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/offspring.py tests/test_pia_llso_offspring.py
git commit -m "feat: add LLSO offspring generation"
```

---

## Task 3: Simulation Batch Contract

**Files:**

- Create: `src/goa_eval/pia_ca_llso/simulation_contract.py`
- Test: `tests/test_pia_simulation_contract.py`

**Step 1: Write failing tests**

Required tests:

- `test_build_simulation_batch_preserves_selected_order`
- `test_simulation_batch_contains_constraint_plan_and_window`
- `test_simulation_batch_marks_rows_pending_and_must_resimulate`
- `test_simulation_manifest_records_boundary`

Expected fields:

- `candidate_id`
- `generation`
- parameter columns
- `selected_rank`
- `simulation_window`
- `constraint_eval_plan_json`
- `evidence_state`
- `must_resimulate`
- `data_source`
- `engineering_validity`

**Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_pia_simulation_contract.py -q
```

Expected: FAIL.

**Step 3: Implement batch builder**

Public API:

```python
def build_simulation_batch(
    selected: pd.DataFrame,
    config: dict,
    generation: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    ...
```

Manifest must include:

```python
{
    "generation": generation,
    "candidate_count": len(batch),
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
    "claim_boundary": "candidate suggestions require simulation before claims",
}
```

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/simulation_contract.py tests/test_pia_simulation_contract.py
git commit -m "feat: add PIA simulation batch contract"
```

---

## Task 4: Simulation Result Import

**Files:**

- Extend: `src/goa_eval/pia_ca_llso/simulation_contract.py`
- Test: `tests/test_pia_simulation_contract.py`

**Step 1: Write failing tests**

Required tests:

- `test_import_simulation_results_requires_candidate_id_score_and_hard_pass`
- `test_import_simulation_results_keeps_only_selected_candidate_ids`
- `test_import_simulation_results_appends_generation_metadata`
- `test_import_simulation_results_rejects_missing_required_columns`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Implement result importer**

Public API:

```python
def import_simulation_results(
    result_csv: str | Path,
    simulation_batch: pd.DataFrame,
    config: dict,
    generation: int,
) -> pd.DataFrame:
    ...
```

Rules:

- require configured result columns;
- keep only rows whose `candidate_id` is in the simulation batch;
- merge missing parameter columns from the simulation batch;
- set `generation`, `source = simulation_result`, `data_source = real_simulation_csv`, `engineering_validity = simulation_only`;
- set `must_resimulate = false` only for imported result rows, because they are now evaluated simulation evidence; do not use this field to imply physical validation.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/simulation_contract.py tests/test_pia_simulation_contract.py
git commit -m "feat: import PIA simulation results"
```

---

## Task 5: Optional External Simulator Executor

**Files:**

- Create: `src/goa_eval/pia_ca_llso/simulation_executor.py`
- Test: `tests/test_pia_simulation_executor.py`

**Step 1: Write failing tests**

Required tests:

- `test_offline_executor_returns_pending_status`
- `test_result_import_executor_loads_generation_result_csv`
- `test_external_command_executor_renders_candidate_file_and_reads_result`
- `test_external_command_executor_fails_closed_on_missing_result`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Implement executor modes**

Public API:

```python
def run_simulation_step(
    simulation_batch: pd.DataFrame,
    output_dir: Path,
    config: dict,
    generation: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    ...
```

Modes:

- `offline`: write batch and return empty imported results with status `pending_simulation`.
- `import_results`: read configured result file or glob from generation directory.
- `external_command`: for each candidate, write `candidate_input.csv`, call command template, then import result file.

Command template variables:

- `{candidate_csv}`
- `{result_csv}`
- `{candidate_id}`
- `{generation}`
- `{output_dir}`

Fail-closed rules:

- non-zero command exit raises `RuntimeError`;
- missing result file raises `FileNotFoundError`;
- malformed result file raises `ValueError`;
- no mock pass is allowed in closed-loop mode.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/simulation_executor.py tests/test_pia_simulation_executor.py
git commit -m "feat: add PIA simulation executor"
```

---

## Task 6: Evolution Orchestrator

**Files:**

- Create: `src/goa_eval/pia_ca_llso/evolution.py`
- Test: `tests/test_pia_evolution_loop.py`

**Step 1: Write failing tests**

Required tests:

- `test_evolution_offline_writes_first_generation_batch`
- `test_evolution_import_results_appends_history_and_runs_next_generation`
- `test_evolution_stops_when_target_score_reached`
- `test_evolution_stops_when_patience_exhausted`
- `test_evolution_preserves_simulation_only_boundary`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Implement orchestrator**

Public API:

```python
def run_evolution_loop(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    config: dict,
    output_dir: Path,
    strategy: str = "classifier_level_hybrid",
    generations: int | None = None,
    offspring_per_generation: int | None = None,
    top_k: int | None = None,
    random_seed: int = 42,
) -> dict[str, object]:
    ...
```

Per generation:

- call `generate_llso_offspring()`;
- combine seed candidates and offspring;
- call existing `suggest_next_run()`;
- call `build_simulation_batch()`;
- call `run_simulation_step()`;
- append imported results to current history;
- write generation artifacts;
- update convergence state.

Stop reasons:

- `target_score_reached`
- `max_generations`
- `simulation_budget_exhausted`
- `no_improvement_patience_exhausted`
- `pending_simulation_results`
- `no_offspring_generated`

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/evolution.py tests/test_pia_evolution_loop.py
git commit -m "feat: orchestrate PIA closed-loop evolution"
```

---

## Task 7: CLI Command `pia-evolve`

**Files:**

- Modify: `src/goa_eval/cli_commands/pia_ca_llso.py`
- Test: `tests/test_pia_cli.py`
- Test: `tests/test_cli_command_registration.py`

**Step 1: Write failing tests**

Required tests:

- `test_pia_evolve_cli_offline_smoke_writes_generation_batch`
- `test_pia_evolve_cli_import_results_runs_two_generations`
- `test_cli_registration_includes_pia_evolve`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Add parser and handler**

CLI args:

```text
pia-evolve
  --history-csv
  --candidate-csv
  --config
  --output-dir
  --strategy
  --generations
  --offspring-per-generation
  --top-k
  --mode
  --simulation-results-dir
  --external-command
  --target-score
  --seed
```

Handler:

- load config/history/candidates with existing adapters;
- override config values from CLI args;
- call `run_evolution_loop()`;
- write `evolution_summary.json`;
- print output path only.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/cli_commands/pia_ca_llso.py tests/test_pia_cli.py tests/test_cli_command_registration.py
git commit -m "feat: add pia-evolve CLI"
```

---

## Task 8: Reports and Documentation

**Files:**

- Create: `docs/pia_ca_llso_closed_loop.md`
- Modify: `docs/pia_ca_llso.md`
- Modify: `docs/pia_ca_llso_api.md`
- Test: `tests/test_pia_report.py`

**Step 1: Write failing tests**

Required tests:

- `test_evolution_report_includes_stop_reason_and_boundary`
- `test_evolution_report_lists_generation_artifacts`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Implement report renderer**

Add a small renderer in `src/goa_eval/pia_ca_llso/report.py`:

```python
def render_evolution_report(summary: dict[str, object]) -> str:
    ...
```

Report must include:

- final stop reason;
- best simulation score;
- generation count;
- simulation budget used;
- path to latest simulation batch;
- `data_source = real_simulation_csv`;
- `engineering_validity = simulation_only`;
- `must_resimulate` semantics.

**Step 4: Update docs**

Document:

- offline mode;
- import-results mode;
- external-command mode;
- required result CSV fields;
- claim boundary.

**Step 5: Run tests**

Expected: PASS.

**Step 6: Commit**

```bash
git add docs/pia_ca_llso_closed_loop.md docs/pia_ca_llso.md docs/pia_ca_llso_api.md src/goa_eval/pia_ca_llso/report.py tests/test_pia_report.py
git commit -m "docs: document PIA closed-loop evolution"
```

---

## Task 9: Benchmark Integration

**Files:**

- Modify: `src/goa_eval/pia_ca_llso/benchmark.py`
- Test: `tests/test_pia_benchmark.py`

**Step 1: Write failing tests**

Required tests:

- `test_pia_benchmark_accepts_evolution_summary`
- `test_pia_benchmark_reports_budget_to_target_score`
- `test_pia_benchmark_keeps_closed_loop_separate_from_single_step_strategies`

**Step 2: Run tests**

Expected: FAIL.

**Step 3: Implement benchmark fields**

Add optional closed-loop benchmark summary:

- `generations_run`
- `simulations_used`
- `best_score`
- `target_reached`
- `stop_reason`
- `best_candidate_id`

Do not mix these with single-step strategy hit-rate unless clearly labeled.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/benchmark.py tests/test_pia_benchmark.py
git commit -m "feat: benchmark PIA closed-loop evolution"
```

---

## Task 10: End-to-End Verification

**Files:**

- Use existing sample CSV files:
  - `examples/pia_ca_llso/sample_history.csv`
  - `examples/pia_ca_llso/sample_candidates.csv`
- Optional create:
  - `examples/pia_ca_llso/sample_generation_000_results.csv`

**Step 1: Run focused tests**

```bash
python -m pytest \
  tests/test_pia_evolution_state.py \
  tests/test_pia_llso_offspring.py \
  tests/test_pia_simulation_contract.py \
  tests/test_pia_simulation_executor.py \
  tests/test_pia_evolution_loop.py \
  tests/test_pia_cli.py \
  tests/test_pia_benchmark.py \
  -q
```

Expected: PASS.

**Step 2: Run existing PIA regression suite**

```bash
python -m pytest tests -k pia -q
```

Expected: PASS.

**Step 3: Run offline CLI smoke**

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
  --output-dir outputs/pia_evolve_offline_smoke
```

Expected:

- `outputs/pia_evolve_offline_smoke/generation_000/simulation_batch.csv` exists.
- `evolution_summary.json` has `stop_reason = pending_simulation_results`.

**Step 4: Run import-results CLI smoke**

Prepare a tiny results CSV with selected `candidate_id` values from generation 000, then run:

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
  --simulation-results-dir examples/pia_ca_llso \
  --output-dir outputs/pia_evolve_import_smoke
```

Expected:

- `evolution_history.csv` includes imported simulation rows.
- `generation_state.jsonl` has at least one imported generation.

**Step 5: Run full regression**

```bash
python -m pytest tests -q
```

Expected: PASS or only known unrelated warnings.

**Step 6: Commit final integration fixes**

```bash
git status --short
git add src/goa_eval/pia_ca_llso src/goa_eval/cli_commands/pia_ca_llso.py config docs tests examples/pia_ca_llso
git commit -m "feat: complete PIA closed-loop evolution"
```

---

## Acceptance Criteria

The closed loop is complete when all are true:

- `pia-evolve --mode offline` writes a generation simulation batch without requiring real simulator access.
- `pia-evolve --mode import_results` can append result CSV rows and continue to the next generation.
- `pia-evolve --mode external_command` can fail closed when the simulator command or result file fails.
- LLSO offspring are generated from level-based learning, not just random sampling.
- Existing `pia-suggest`, `pia-benchmark`, `adaptive_pia_capm`, and `classifier_level_hybrid` behavior remains compatible.
- Every pre-simulation suggestion has `must_resimulate = true`.
- Every imported simulator result keeps `data_source = real_simulation_csv` and `engineering_validity = simulation_only`.
- Reports distinguish suggestion, simulation evidence, and physical validation.
- Tests cover generation state, offspring generation, simulation batch contracts, result import, CLI smoke, and existing PIA regressions.

---

## Risks and Guardrails

- Risk: external simulator integration becomes tool-specific too early.
  - Guardrail: use a command-template executor first; add Empyrean-specific adapter only after the CSV contract is stable.
- Risk: generated offspring leave valid electrical ranges.
  - Guardrail: infer bounds conservatively and skip unbounded parameters.
- Risk: classifier feedback amplifies bad early labels.
  - Guardrail: keep CAPM barrier and constraint-ledger repair in the loop; preserve fallback behavior for insufficient data.
- Risk: reports overclaim results.
  - Guardrail: keep `engineering_validity = simulation_only` visible in every artifact and report.
- Risk: closed-loop benchmark is compared unfairly with single-step selectors.
  - Guardrail: report simulation budget and generations separately.
