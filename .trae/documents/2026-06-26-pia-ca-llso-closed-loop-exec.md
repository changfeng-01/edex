# PIA-CA-LLSO Closed Loop 执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> **Spec reference:** The full specification is at `docs/plans/2026-06-26-pia-ca-llso-closed-loop.md` (uploaded document). All detailed code examples, test shapes, and config snippets are in that document.
> **Repository:** `D:\EDA大赛`

**Goal:** Build a full PIA-CA-LLSO evolutionary closed loop that generates LLSO offspring, selects simulation batches, runs or imports simulation evidence, appends verified results to history, retrains models, and repeats until budget or convergence.

**Architecture:** Keep the current `pia-suggest` stack as the single-generation selection engine. Add a thin evolution layer: generation state, LLSO offspring, simulation batch contracts, result import/execution, history append, and convergence checks. Preserve: `data_source = real_simulation_csv`, `engineering_validity = simulation_only`, `must_resimulate = true`.

**Tech Stack:** Python 3.10+, pandas, numpy, PyYAML, argparse, existing `goa_eval.pia_ca_llso` modules, pytest.

**Methodology:** TDD (test-driven-development) — write failing test first, watch it fail, write minimal code, verify pass, refactor, commit.

---

## Verification Corrections (Applied to Spec)

The following corrections from codebase verification MUST be applied when implementing:

| # | Location | Correction |
|---|----------|------------|
| 1 | All new modules | Use `Mapping[str, Any]` instead of `dict` for config parameter (matches existing codebase style) |
| 2 | `evolution_state.py` | Remove `must_resimulate` from `GenerationState` dataclass (it's a row-level field, not generation-level) |
| 3 | `simulation_contract.py` | `build_simulation_batch()` wraps already-scheduled candidates from `suggest_next_run()`; does NOT re-schedule |
| 4 | `evolution.py` | Only concatenate offspring + seed candidates; pass to `suggest_next_run()` (repair candidates auto-generated internally) |
| 5 | YAML configs | Remove `evolution_loop.target_score` (reuse top-level `target_score`); insert new sections after `benchmark`, before `metadata` |
| 6 | Tests | Use `assert payload["must_resimulate"]` instead of `assert payload["must_resimulate"] is True` |
| 7 | `test_cli_command_registration.py` | Add `"pia-evolve"` entry to `COMMAND_ARGV` dict |
| 8 | `offspring.py` | Add docstring distinguishing from `candidate_generator.py`'s simple elite-mutation |
| 9 | `__init__.py` | Add `run_evolution_loop` to public exports |
| 10 | `io.py` | May need `write_jsonl` helper; or inline in calling modules |

---

## Key Existing APIs (Do Not Duplicate)

- `suggest_next_run(history, candidates, config, strategy, top_k)` → `SelectionResult` — already calls `generate_constraint_repair_candidates()` and `attach_evaluation_schedule()` internally
- `assign_level_labels(history, config)` → labeled DataFrame with `level` column
- `read_config(path)`, `ensure_output_dir(path)`, `write_json(data, path)`, `write_csv(df, path)`, `read_csv(path)`
- `HistoryAdapter(df).adapt()`, `CandidateAdapter(df).adapt()`
- `DATA_SOURCE = "real_simulation_csv"`, `ENGINEERING_VALIDITY = "simulation_only"` (from `__init__.py`)

---

## Task Execution Order

### Task 1: Generation State Schema
- **Create:** `src/goa_eval/pia_ca_llso/evolution_state.py`
- **Test:** `tests/test_pia_evolution_state.py`
- Follow spec Step 1-5 in uploaded document, applying corrections #2 and #6

### Task 2: LLSO Offspring Generator
- **Create:** `src/goa_eval/pia_ca_llso/offspring.py`
- **Test:** `tests/test_pia_llso_offspring.py`
- Follow spec Step 1-5, applying corrections #1 and #8
- LLSO formula: `child = learner + r1*(teacher - learner) + r2*(elite - learner) + noise`

### Task 3: Simulation Batch Contract
- **Create:** `src/goa_eval/pia_ca_llso/simulation_contract.py`
- **Test:** `tests/test_pia_simulation_contract.py`
- Follow spec Step 1-5, applying correction #3 (wrap, don't re-schedule)

### Task 4: Simulation Result Import
- **Extend:** `src/goa_eval/pia_ca_llso/simulation_contract.py`
- **Test:** Extend `tests/test_pia_simulation_contract.py`
- Follow spec Step 1-5, applying correction #1

### Task 5: External Simulator Executor
- **Create:** `src/goa_eval/pia_ca_llso/simulation_executor.py`
- **Test:** `tests/test_pia_simulation_executor.py`
- Follow spec Step 1-5
- Three modes: offline, import_results, external_command (fail-closed)

### Task 6: Evolution Orchestrator
- **Create:** `src/goa_eval/pia_ca_llso/evolution.py`
- **Test:** `tests/test_pia_evolution_loop.py`
- Follow spec Step 1-5, applying corrections #1 and #4
- Per-generation flow: label → offspring → concat → suggest_next_run → build_batch → run_simulation → append

### Task 7: CLI Command `pia-evolve`
- **Modify:** `src/goa_eval/cli_commands/pia_ca_llso.py`
- **Modify:** `tests/test_cli_command_registration.py` (apply correction #7)
- **Extend:** `tests/test_pia_cli.py`
- Follow spec Step 1-5

### Task 8: Reports and Documentation
- **Extend:** `src/goa_eval/pia_ca_llso/report.py` (add `render_evolution_report`)
- **Create:** `docs/pia_ca_llso_closed_loop.md`
- **Modify:** `docs/pia_ca_llso.md`, `docs/pia_ca_llso_api.md`
- **Extend:** `tests/test_pia_report.py`

### Task 9: Benchmark Integration
- **Modify:** `src/goa_eval/pia_ca_llso/benchmark.py`
- **Extend:** `tests/test_pia_benchmark.py`

### Task 10: End-to-End Verification
- Run focused tests: `pytest tests/test_pia_evolution_state.py tests/test_pia_llso_offspring.py tests/test_pia_simulation_contract.py tests/test_pia_simulation_executor.py tests/test_pia_evolution_loop.py tests/test_pia_cli.py tests/test_pia_benchmark.py -q`
- Run PIA regression: `pytest tests -k pia -q` (baseline: 45 passed)
- Run offline CLI smoke: `python -m goa_eval.cli pia-evolve --mode offline ...`
- Run import-results CLI smoke
- Run full regression: `pytest tests -q`

---

## Acceptance Criteria

- `pia-evolve --mode offline` writes a generation simulation batch without requiring real simulator access
- `pia-evolve --mode import_results` appends result CSV rows and continues to next generation
- `pia-evolve --mode external_command` fails closed when simulator command or result file fails
- LLSO offspring are generated from level-based learning, not just random sampling
- Existing `pia-suggest`, `pia-benchmark`, `adaptive_pia_capm`, `classifier_level_hybrid` behavior remains compatible
- Every pre-simulation suggestion has `must_resimulate = true`
- Every imported simulator result keeps `data_source = real_simulation_csv` and `engineering_validity = simulation_only`
- Tests cover all new modules + existing PIA regressions still pass