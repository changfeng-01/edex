# PIA-CA-LLSO Phase 2 Real Simulation Closed Loop Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the completed Phase 1 `pia-evolve` loop into a robust real-simulation workflow with resumable generations, strict result schemas, simulator adapters, closed-loop reports, and budget-aware benchmark evidence.

**Architecture:** Keep Phase 1 as the core loop: LLSO offspring -> existing `suggest_next_run()` -> simulation batch -> result import -> history append. Phase 2 adds reliability around that loop: generation artifact completeness, resume support, result validation, simulator adapter contracts, and benchmark/reporting that proves each improvement came from imported simulation evidence.

**Tech Stack:** Python, pandas, argparse CLI, existing `goa_eval.pia_ca_llso` modules, pytest, subprocess-based simulator command integration, existing evidence boundary fields.

---

## Current Phase 1 Baseline

The repository already has:

- `src/goa_eval/pia_ca_llso/evolution.py`
- `src/goa_eval/pia_ca_llso/evolution_state.py`
- `src/goa_eval/pia_ca_llso/offspring.py`
- `src/goa_eval/pia_ca_llso/simulation_contract.py`
- `src/goa_eval/pia_ca_llso/simulation_executor.py`
- `pia-evolve` registered in `src/goa_eval/cli_commands/pia_ca_llso.py`
- tests for evolution state, LLSO offspring, simulation contract, simulation executor, evolution loop, and CLI registration.

Phase 1 proves the loop shape. Phase 2 should not replace it. Phase 2 should make it usable for real experiment rounds.

Preserve these exact boundaries:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Pre-simulation candidate suggestions keep `must_resimulate = true`. Imported simulation result rows may set `must_resimulate = false`, but they still remain `engineering_validity = simulation_only`.

---

## Phase 2 Scope

Do these in order:

1. Complete generation artifacts and reports.
2. Add resumable evolution from a pending generation.
3. Strengthen simulation-result schema validation.
4. Add a deterministic local simulator fixture for end-to-end tests.
5. Add an Empyrean/SPICE adapter boundary, initially command-template based.
6. Add closed-loop benchmark metrics.
7. Add guardrails for overclaiming and result leakage.

Do not add another ranking strategy in Phase 2. The next bottleneck is operational trust, not scoring formula complexity.

---

## Task 1: Complete Per-Generation Artifacts

**Files:**

- Modify: `src/goa_eval/pia_ca_llso/evolution.py`
- Modify: `src/goa_eval/pia_ca_llso/report.py`
- Test: `tests/test_pia_evolution_loop.py`
- Test: `tests/test_pia_report.py`

**Step 1: Write failing tests**

Add tests asserting each generation writes:

- `offspring_candidates.csv`
- `pia_selected_candidates.csv`
- `simulation_batch.csv`
- `simulation_manifest.json`
- `generation_summary.json`
- `imported_results.csv` when results are imported
- `evolution_report.md` at root

**Step 2: Run focused tests**

```bash
python -m pytest tests/test_pia_evolution_loop.py tests/test_pia_report.py -q
```

Expected: FAIL because Phase 1 currently writes only part of the documented artifact set.

**Step 3: Implement minimal artifact writes**

In `run_evolution_loop()`:

- write `offspring` before selection;
- write `selected` after `suggest_next_run()`;
- write imported results, even if empty, with headers where possible;
- write a compact `generation_summary.json`;
- call `render_evolution_report(summary)` after final summary is known.

**Step 4: Rerun tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/evolution.py src/goa_eval/pia_ca_llso/report.py tests/test_pia_evolution_loop.py tests/test_pia_report.py
git commit -m "feat: complete PIA evolution generation artifacts"
```

---

## Task 2: Add Resume Support

**Files:**

- Modify: `src/goa_eval/pia_ca_llso/evolution.py`
- Modify: `src/goa_eval/cli_commands/pia_ca_llso.py`
- Test: `tests/test_pia_evolution_loop.py`
- Test: `tests/test_pia_cli.py`

**Step 1: Write failing tests**

Add tests:

- `test_evolution_resume_from_existing_history_and_state`
- `test_pia_evolve_resume_imports_pending_generation_results`
- `test_resume_rejects_mismatched_candidate_ids`

**Step 2: CLI design**

Add:

```text
pia-evolve --resume-from outputs/pia_evolve_run
pia-evolve --resume-generation 0
```

Behavior:

- load `evolution_history.csv` from `--resume-from`;
- load pending `generation_XXX/simulation_batch.csv`;
- import result files for that pending batch;
- append results;
- continue from next generation.

**Step 3: Implement**

Keep implementation small:

- helper `load_resume_state(output_dir, generation)`;
- validate config problem name and parameter columns if available;
- fail closed if pending batch is missing.

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_evolution_loop.py tests/test_pia_cli.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/evolution.py src/goa_eval/cli_commands/pia_ca_llso.py tests/test_pia_evolution_loop.py tests/test_pia_cli.py
git commit -m "feat: resume PIA evolution from pending generation"
```

---

## Task 3: Strengthen Result Schema Validation

**Files:**

- Modify: `src/goa_eval/pia_ca_llso/simulation_contract.py`
- Create: `src/goa_eval/pia_ca_llso/result_schema.py`
- Test: `tests/test_pia_simulation_contract.py`

**Step 1: Write failing tests**

Add tests:

- reject duplicated `candidate_id` rows unless explicitly configured;
- reject non-numeric `overall_score`;
- reject missing parameter columns when they cannot be recovered from batch;
- reject result rows that modify candidate parameters compared with the batch;
- preserve allowed metric columns and CAPM constraint columns;
- write validation warnings for extra columns instead of dropping them silently.

**Step 2: Implement**

Create:

```python
def validate_simulation_results(results, simulation_batch, config) -> tuple[pd.DataFrame, dict]:
    ...
```

Validation must return a cleaned frame plus a machine-readable validation report.

**Step 3: Wire into importer**

`import_simulation_results()` should call the validator before merging into history.

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_simulation_contract.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/simulation_contract.py src/goa_eval/pia_ca_llso/result_schema.py tests/test_pia_simulation_contract.py
git commit -m "feat: validate PIA simulation result schema"
```

---

## Task 4: Add Deterministic Local Simulator Fixture

**Files:**

- Create: `src/goa_eval/pia_ca_llso/local_simulator.py`
- Modify: `src/goa_eval/pia_ca_llso/simulation_executor.py`
- Test: `tests/test_pia_simulation_executor.py`
- Test: `tests/test_pia_evolution_loop.py`

**Step 1: Write failing tests**

Add tests:

- `test_local_fixture_simulator_produces_result_csv`
- `test_evolution_runs_two_generations_with_local_fixture_simulator`
- `test_local_fixture_results_remain_simulation_only`

**Step 2: Implement local deterministic mode**

Add executor mode:

```yaml
simulation_executor:
  mode: local_fixture
```

This is not a physical simulator. It is a deterministic test fixture that maps parameters to plausible scores and constraints for CI-style closed-loop testing.

**Step 3: Guardrail**

Every output must include:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
simulator_mode = local_fixture
```

Do not use this mode for scientific claims.

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_simulation_executor.py tests/test_pia_evolution_loop.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/local_simulator.py src/goa_eval/pia_ca_llso/simulation_executor.py tests/test_pia_simulation_executor.py tests/test_pia_evolution_loop.py
git commit -m "test: add deterministic PIA local simulator fixture"
```

---

## Task 5: Add External Simulator Adapter Contract

**Files:**

- Create: `src/goa_eval/pia_ca_llso/simulator_adapter.py`
- Modify: `src/goa_eval/pia_ca_llso/simulation_executor.py`
- Create: `docs/pia_ca_llso_simulator_adapter.md`
- Test: `tests/test_pia_simulation_executor.py`

**Step 1: Write failing tests**

Add tests:

- command template receives `candidate_csv`, `result_csv`, `generation`, `output_dir`;
- adapter records command, exit code, stdout/stderr snippets;
- failed command raises `RuntimeError`;
- successful command without result file raises `RuntimeError`;
- result file with mismatched candidate IDs is rejected.

**Step 2: Implement adapter record**

Each external run writes:

- `simulator_invocation.json`
- `simulator_stdout.txt`
- `simulator_stderr.txt`

**Step 3: Document command contract**

Document the expected external result CSV fields:

- `candidate_id`
- `overall_score`
- `hard_constraint_passed`
- optional metric columns such as delay, power, waveform metrics, constraint ledger fields.

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_simulation_executor.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/simulator_adapter.py src/goa_eval/pia_ca_llso/simulation_executor.py docs/pia_ca_llso_simulator_adapter.md tests/test_pia_simulation_executor.py
git commit -m "feat: add external simulator adapter contract"
```

---

## Task 6: Closed-Loop Benchmark Metrics

**Files:**

- Modify: `src/goa_eval/pia_ca_llso/benchmark.py`
- Modify: `src/goa_eval/cli_commands/pia_ca_llso.py`
- Test: `tests/test_pia_benchmark.py`

**Step 1: Write failing tests**

Add tests:

- `test_closed_loop_benchmark_reports_budget_to_best`
- `test_closed_loop_benchmark_reports_generations_to_target`
- `test_closed_loop_benchmark_separates_imported_results_from_suggestions`

**Step 2: Add benchmark fields**

Fields:

- `best_score_initial`
- `best_score_final`
- `best_score_delta`
- `target_reached`
- `generations_run`
- `simulations_used`
- `budget_to_target`
- `stop_reason`
- `imported_result_count`
- `suggestion_count`

**Step 3: Wire CLI option**

Either add a separate `pia-evolve-benchmark` command or add an option to `pia-benchmark`:

```text
pia-benchmark --closed-loop
```

Prefer the smaller change that fits current CLI structure.

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_benchmark.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/benchmark.py src/goa_eval/cli_commands/pia_ca_llso.py tests/test_pia_benchmark.py
git commit -m "feat: benchmark PIA closed-loop evolution"
```

---

## Task 7: Claim-Boundary Audit

**Files:**

- Create: `src/goa_eval/pia_ca_llso/boundary_audit.py`
- Test: `tests/test_pia_boundary_audit.py`
- Modify docs as needed.

**Step 1: Write failing tests**

Audit must flag:

- missing `engineering_validity`;
- any value other than `simulation_only`;
- suggestion rows missing `must_resimulate = true`;
- report text claiming physical/silicon/lab/tapeout validation;
- imported rows missing `data_source = real_simulation_csv`.

**Step 2: Implement**

Small API:

```python
def audit_evolution_outputs(output_dir: Path) -> dict[str, object]:
    ...
```

Return:

- `passed`
- `issues`
- `checked_files`

**Step 3: Add optional CLI flag**

```text
pia-evolve --audit-boundary
```

**Step 4: Verify**

```bash
python -m pytest tests/test_pia_boundary_audit.py tests/test_pia_cli.py -q
```

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/boundary_audit.py tests/test_pia_boundary_audit.py src/goa_eval/cli_commands/pia_ca_llso.py
git commit -m "feat: audit PIA evolution evidence boundary"
```

---

## Phase 2 Verification

Run focused tests:

```bash
python -m pytest \
  tests/test_pia_evolution_loop.py \
  tests/test_pia_simulation_contract.py \
  tests/test_pia_simulation_executor.py \
  tests/test_pia_cli.py \
  tests/test_pia_benchmark.py \
  tests/test_pia_report.py \
  -q
```

Run full PIA suite:

```bash
python -m pytest tests -k pia -q
```

Run smoke tests:

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
  --output-dir outputs/pia_evolve_phase2_offline
```

```bash
python -m goa_eval.cli pia-evolve \
  --history-csv examples/pia_ca_llso/sample_history.csv \
  --candidate-csv examples/pia_ca_llso/sample_candidates.csv \
  --config config/pia_ca_llso_goa_profile.yaml \
  --strategy classifier_level_hybrid \
  --generations 3 \
  --offspring-per-generation 8 \
  --top-k 4 \
  --mode local_fixture \
  --output-dir outputs/pia_evolve_phase2_local_fixture
```

Expected:

- offline run stops with `pending_simulation_results`;
- local fixture run completes multiple generations without external tools;
- all reports keep `engineering_validity = simulation_only`;
- no generated output is committed except intentionally small test fixtures.

---

## Phase 2 Acceptance Criteria

Phase 2 is complete when:

- A pending `pia-evolve` run can be resumed after result CSVs arrive.
- Each generation has complete artifacts for inspection and replay.
- Bad result files fail with clear validation errors.
- A deterministic local simulator fixture proves multi-generation closed-loop behavior in tests.
- External simulator runs leave invocation evidence and fail closed.
- Benchmark output reports improvement per simulation budget, not just final score.
- Boundary audit catches overclaiming and missing simulation-only fields.
