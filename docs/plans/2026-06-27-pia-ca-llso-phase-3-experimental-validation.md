# PIA-CA-LLSO Phase 3 Experimental Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reproducible experimental validation layer that proves whether the completed PIA-CA-LLSO closed loop outperforms its baselines under fixed budgets, multiple seeds, ablations, and simulation-only evidence boundaries.

**Architecture:** Keep `pia-evolve` as the optimizer under test. Add a validation layer around it: experiment protocol definitions, scenario manifests, strategy/ablation runners, multi-seed result aggregation, statistical summaries, boundary audits, and paper-ready validation reports. The validation layer must separate suggestions from imported simulation evidence and must never claim physical validation.

**Tech Stack:** Python, pandas, numpy, argparse CLI, existing `goa_eval.pia_ca_llso` Phase 2 modules, pytest, Markdown/CSV/JSON artifacts, no new external dependencies.

---

## Required Starting State

Phase 2 is complete on `codex/pia-phase2-closed-loop` and merged into `origin/main` by PR #32:

```text
e420b919 Merge pull request #32 from changfeng-01/codex/pia-phase2-closed-loop
```

Before implementing Phase 3, sync the local working branch:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b codex/pia-phase3-experimental-validation
```

Do not touch `.trae/`.

Run the Phase 2 baseline:

```bash
python -m pytest tests -k pia -q
```

Expected current baseline after Phase 2:

```text
88 passed, 307 deselected, 1 warning
```

Preserve these exact evidence labels in every generated report and machine-readable artifact:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Interpretation:

- candidate suggestions are not validated improvements;
- imported simulator rows are evaluated simulation evidence, still not physical validation;
- paper-derived or local-fixture rows must not be presented as reproduced real simulator evidence.

---

## Phase 3 Scientific Design

The question Phase 3 answers:

```text
Does full PIA-CA-LLSO closed-loop evolution reach better simulation-only outcomes
than fixed baselines under the same budget and scenario protocol?
```

Primary outcome:

- `simulations_to_target`: number of imported simulation results needed to reach target score.

Secondary outcomes:

- `target_hit_rate`
- `best_score_final`
- `best_score_delta`
- `convergence_auc`
- `hard_pass_rate`
- `mean_constraint_violation`
- `boundary_audit_passed`
- `invalid_result_rejection_count`

Required comparison methods:

- `random`
- `ca_llso_raw_distance`
- `pia_capm_distance`
- `adaptive_pia_capm`
- `classifier_level_hybrid`
- `pia_evolve_full`

Required ablations:

- `full`
- `no_classifier`
- `no_adaptive_capm`
- `no_constraint_repair`
- `no_llso_offspring`
- `no_evaluation_scheduler`
- `capm_only`

Minimum experimental design:

- 3 scenarios
- 5 seeds per scenario
- 6 comparison methods
- 7 ablation settings
- fixed budget tiers: 20, 50, 100 simulations

For quick development, support a `--smoke` mode with 1 scenario, 2 seeds, and budget 8.

---

## Task 1: Validation Protocol Schema

**Files:**

- Create: `src/goa_eval/pia_ca_llso/validation_protocol.py`
- Create: `config/pia_ca_llso_validation_protocol.yaml`
- Test: `tests/test_pia_validation_protocol.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_validation_protocol_loads_required_methods_and_ablation_settings(): ...
def test_validation_protocol_rejects_missing_primary_outcome(): ...
def test_validation_protocol_expands_budget_seed_scenario_grid(): ...
def test_validation_protocol_preserves_boundary_labels(): ...
```

**Step 2: Run the failing test**

```bash
python -m pytest tests/test_pia_validation_protocol.py -q
```

Expected: FAIL because `validation_protocol.py` does not exist.

**Step 3: Implement minimal protocol API**

Public API:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class ValidationRunSpec:
    scenario_id: str
    method: str
    ablation: str
    seed: int
    budget: int
    target_score: float


def load_validation_protocol(path: str | Path) -> dict[str, Any]:
    ...


def expand_validation_grid(protocol: Mapping[str, Any]) -> list[ValidationRunSpec]:
    ...


def validate_protocol(protocol: Mapping[str, Any]) -> None:
    ...
```

Default config:

```yaml
name: pia_ca_llso_phase3_validation
primary_outcome: simulations_to_target
target_score: 80
budgets: [20, 50, 100]
seeds: [11, 23, 37, 41, 53]
methods:
  - random
  - ca_llso_raw_distance
  - pia_capm_distance
  - adaptive_pia_capm
  - classifier_level_hybrid
  - pia_evolve_full
ablations:
  - full
  - no_classifier
  - no_adaptive_capm
  - no_constraint_repair
  - no_llso_offspring
  - no_evaluation_scheduler
  - capm_only
scenarios:
  - scenario_id: sample_goa
    history_csv: examples/pia_ca_llso/sample_history.csv
    candidate_csv: examples/pia_ca_llso/sample_candidates.csv
    config: config/pia_ca_llso_goa_profile.yaml
boundary:
  data_source: real_simulation_csv
  engineering_validity: simulation_only
  must_resimulate: true
```

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/validation_protocol.py config/pia_ca_llso_validation_protocol.yaml tests/test_pia_validation_protocol.py
git commit -m "feat: add PIA validation protocol schema"
```

---

## Task 2: Scenario Registry

**Files:**

- Create: `src/goa_eval/pia_ca_llso/scenario_registry.py`
- Create: `examples/pia_ca_llso/scenarios/sample_goa.yaml`
- Test: `tests/test_pia_scenario_registry.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_scenario_registry_loads_history_candidates_and_config(): ...
def test_scenario_registry_rejects_missing_files(): ...
def test_scenario_registry_records_claim_boundary(): ...
def test_scenario_registry_supports_local_fixture_marker(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_scenario_registry.py -q
```

Expected: FAIL.

**Step 3: Implement registry API**

Public API:

```python
def load_scenario(scenario_entry: Mapping[str, Any]) -> dict[str, Any]:
    ...


def validate_scenario_bundle(bundle: Mapping[str, Any]) -> None:
    ...
```

Scenario output must contain:

- `scenario_id`
- `history`
- `candidates`
- `config`
- `history_csv`
- `candidate_csv`
- `boundary`
- `source_type`

For local fixtures, set:

```yaml
source_type: local_fixture
claim_boundary: CI fixture for closed-loop behavior only
```

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/scenario_registry.py examples/pia_ca_llso/scenarios/sample_goa.yaml tests/test_pia_scenario_registry.py
git commit -m "feat: add PIA validation scenario registry"
```

---

## Task 3: Ablation Config Builder

**Files:**

- Create: `src/goa_eval/pia_ca_llso/ablation.py`
- Test: `tests/test_pia_ablation.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_ablation_no_classifier_uses_adaptive_capm_strategy(): ...
def test_ablation_no_constraint_repair_disables_repair_candidates(): ...
def test_ablation_no_llso_offspring_uses_seed_candidates_only(): ...
def test_ablation_no_scheduler_disables_evaluation_scheduler(): ...
def test_ablation_capm_only_uses_pia_capm_distance_and_disables_adaptive_parts(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_ablation.py -q
```

Expected: FAIL.

**Step 3: Implement ablation mapping**

Public API:

```python
def build_ablation_config(base_config: dict, ablation: str) -> tuple[dict, str]:
    ...
```

Return `(config, strategy)`.

Mapping:

- `full`: keep config, strategy `classifier_level_hybrid`.
- `no_classifier`: strategy `adaptive_pia_capm`.
- `no_adaptive_capm`: set `adaptive_capm.enabled = false`, strategy `classifier_level_hybrid`.
- `no_constraint_repair`: set `repair_candidates.enabled = false`.
- `no_llso_offspring`: set `llso_offspring.enabled = false`, `offspring_per_generation = 0`.
- `no_evaluation_scheduler`: set `evaluation_scheduler.enabled = false`.
- `capm_only`: strategy `pia_capm_distance`, disable classifier/adaptive/repair scheduler.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/ablation.py tests/test_pia_ablation.py
git commit -m "feat: add PIA ablation config builder"
```

---

## Task 4: Single Validation Run Executor

**Files:**

- Create: `src/goa_eval/pia_ca_llso/validation_runner.py`
- Test: `tests/test_pia_validation_runner.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_validation_runner_executes_single_local_fixture_run(): ...
def test_validation_runner_writes_run_manifest_and_summary(): ...
def test_validation_runner_runs_boundary_audit(): ...
def test_validation_runner_separates_method_and_ablation_labels(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_validation_runner.py -q
```

Expected: FAIL.

**Step 3: Implement runner**

Public API:

```python
def run_validation_spec(
    spec: ValidationRunSpec,
    scenario_bundle: dict,
    output_root: Path,
    smoke: bool = False,
) -> dict[str, Any]:
    ...
```

Implementation:

- build ablation config;
- force `simulation_executor.mode = local_fixture` for smoke/local validation unless scenario says external/import;
- call `run_evolution_loop()`;
- call `audit_evolution_outputs()`;
- write:
  - `run_manifest.json`
  - `run_summary.json`
  - `boundary_audit.json`

Run directory layout:

```text
outputs/pia_phase3_validation/
  scenario=<id>/
    method=<method>/
      ablation=<ablation>/
        budget=<budget>/
          seed=<seed>/
```

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/validation_runner.py tests/test_pia_validation_runner.py
git commit -m "feat: add PIA validation run executor"
```

---

## Task 5: Multi-Seed Experiment Aggregator

**Files:**

- Create: `src/goa_eval/pia_ca_llso/validation_statistics.py`
- Test: `tests/test_pia_validation_statistics.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_statistics_compute_mean_std_and_hit_rate(): ...
def test_statistics_compute_convergence_auc_from_curve(): ...
def test_statistics_compute_nonparametric_win_rate(): ...
def test_statistics_handles_missing_target_hits(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_validation_statistics.py -q
```

Expected: FAIL.

**Step 3: Implement statistics without new dependencies**

Public API:

```python
def summarize_validation_runs(run_summaries: list[dict[str, Any]]) -> pd.DataFrame:
    ...


def compute_pairwise_win_rates(summary_frame: pd.DataFrame, baseline: str) -> pd.DataFrame:
    ...


def bootstrap_mean_ci(values: Sequence[float], seed: int = 42, n_boot: int = 1000) -> tuple[float, float]:
    ...
```

Required grouped outputs:

- `target_hit_rate`
- `best_score_mean`
- `best_score_std`
- `simulations_to_target_mean`
- `simulations_to_target_median`
- `convergence_auc_mean`
- `hard_pass_rate_mean`
- `boundary_audit_pass_rate`

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/pia_ca_llso/validation_statistics.py tests/test_pia_validation_statistics.py
git commit -m "feat: aggregate PIA validation statistics"
```

---

## Task 6: Validation CLI

**Files:**

- Modify: `src/goa_eval/cli_commands/pia_ca_llso.py`
- Test: `tests/test_pia_cli.py`
- Test: `tests/test_cli_command_registration.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_pia_validate_cli_smoke_runs_protocol(): ...
def test_pia_validate_cli_writes_aggregate_csv_and_report(): ...
def test_cli_registration_includes_pia_validate(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_cli.py tests/test_cli_command_registration.py -q
```

Expected: FAIL.

**Step 3: Add CLI command**

Command:

```text
pia-validate
  --protocol config/pia_ca_llso_validation_protocol.yaml
  --output-dir outputs/pia_phase3_validation
  --smoke
  --max-runs
```

Handler:

- load protocol;
- expand grid;
- optionally reduce grid for smoke;
- run specs;
- aggregate summaries;
- write:
  - `validation_runs.csv`
  - `validation_summary.csv`
  - `pairwise_win_rates.csv`
  - `validation_summary.json`

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add src/goa_eval/cli_commands/pia_ca_llso.py tests/test_pia_cli.py tests/test_cli_command_registration.py
git commit -m "feat: add PIA validation CLI"
```

---

## Task 7: Validation Report

**Files:**

- Create: `src/goa_eval/pia_ca_llso/validation_report.py`
- Create: `docs/pia_ca_llso_experimental_validation.md`
- Test: `tests/test_pia_validation_report.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_validation_report_includes_primary_outcome(): ...
def test_validation_report_includes_ablation_table(): ...
def test_validation_report_includes_boundary_statement(): ...
def test_validation_report_does_not_overclaim_physical_validation(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_validation_report.py -q
```

Expected: FAIL.

**Step 3: Implement report renderer**

Public API:

```python
def render_validation_report(
    protocol: dict[str, Any],
    run_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    win_rate_frame: pd.DataFrame,
) -> str:
    ...
```

Report sections:

- Purpose
- Protocol
- Scenarios
- Methods
- Ablations
- Primary outcome
- Secondary outcomes
- Results summary
- Pairwise win rates
- Failure cases
- Boundary statement
- Limitations
- Next algorithmic upgrades

Boundary statement must include:

```text
engineering_validity = simulation_only
These results are simulation-only evidence, not physical validation.
```

**Step 4: Wire CLI**

`pia-validate` writes:

```text
experimental_validation_report.md
```

**Step 5: Run tests**

Expected: PASS.

**Step 6: Commit**

```bash
git add src/goa_eval/pia_ca_llso/validation_report.py docs/pia_ca_llso_experimental_validation.md tests/test_pia_validation_report.py src/goa_eval/cli_commands/pia_ca_llso.py
git commit -m "docs: add PIA experimental validation report"
```

---

## Task 8: Real Simulation Case Pack Contract

**Files:**

- Create: `docs/pia_ca_llso_real_case_pack.md`
- Create: `examples/pia_ca_llso/real_case_pack_template/README.md`
- Create: `examples/pia_ca_llso/real_case_pack_template/manifest.yaml`
- Test: `tests/test_pia_scenario_registry.py`

**Step 1: Write failing tests**

Add tests:

```python
def test_real_case_pack_manifest_requires_history_candidates_and_results(): ...
def test_real_case_pack_manifest_requires_boundary_fields(): ...
def test_real_case_pack_rejects_paper_digitized_as_real_simulation(): ...
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_pia_scenario_registry.py -q
```

Expected: FAIL.

**Step 3: Define manifest contract**

Template:

```yaml
scenario_id: real_goa_case_001
source_type: real_simulation_csv
history_csv: history.csv
candidate_csv: candidates.csv
result_dirs:
  - generation_000
config: config.yaml
boundary:
  data_source: real_simulation_csv
  engineering_validity: simulation_only
  must_resimulate: true
notes:
  visible_nodes: []
  simulator: TODO
  limitations: []
```

**Step 4: Update registry**

Make `load_scenario()` support manifest paths as scenario entries.

**Step 5: Commit**

```bash
git add docs/pia_ca_llso_real_case_pack.md examples/pia_ca_llso/real_case_pack_template tests/test_pia_scenario_registry.py src/goa_eval/pia_ca_llso/scenario_registry.py
git commit -m "docs: define PIA real simulation case pack"
```

---

## Task 9: Smoke and Full Verification

**Files:**

- No new files unless fixing failures.

**Step 1: Run focused Phase 3 tests**

```bash
python -m pytest \
  tests/test_pia_validation_protocol.py \
  tests/test_pia_scenario_registry.py \
  tests/test_pia_ablation.py \
  tests/test_pia_validation_runner.py \
  tests/test_pia_validation_statistics.py \
  tests/test_pia_validation_report.py \
  tests/test_pia_cli.py \
  -q
```

Expected: PASS.

**Step 2: Run PIA regression suite**

```bash
python -m pytest tests -k pia -q
```

Expected: PASS.

**Step 3: Run smoke CLI**

```bash
python -m goa_eval.cli pia-validate \
  --protocol config/pia_ca_llso_validation_protocol.yaml \
  --output-dir outputs/pia_phase3_validation_smoke \
  --smoke
```

Expected outputs:

- `validation_runs.csv`
- `validation_summary.csv`
- `pairwise_win_rates.csv`
- `validation_summary.json`
- `experimental_validation_report.md`

**Step 4: Run boundary audit over smoke outputs**

Use existing Phase 2 audit function or CLI if available.

Expected:

```text
passed = true
```

**Step 5: Commit final fixes**

```bash
git status --short
git add src/goa_eval/pia_ca_llso src/goa_eval/cli_commands/pia_ca_llso.py config docs examples tests
git commit -m "feat: validate PIA closed-loop experiments"
```

---

## Acceptance Criteria

Phase 3 is complete when:

- `pia-validate --smoke` runs end-to-end with local fixture scenarios.
- The validation protocol expands scenario x method x ablation x seed x budget grids.
- Full closed-loop results are compared against baselines under equal budgets.
- Ablation results quantify which modules contribute.
- Aggregated statistics include mean, std, hit rate, budget-to-target, and win rates.
- The validation report is human-readable and includes limitations.
- Every artifact preserves `engineering_validity = simulation_only`.
- Real simulation case packs have a documented, validated manifest contract.
- No output claims physical, silicon, lab, tapeout, or hardware validation.

---

## Scientific Risk Review

Major risks:

- **Selection bias:** sample scenarios may be too easy or tuned to PIA. Mitigation: include multiple scenarios and report scenario-level results.
- **Overfitting to local fixture:** fixture success does not prove real simulator success. Mitigation: label fixture runs explicitly and require real case packs for final claims.
- **Budget unfairness:** closed-loop methods may receive more information than single-step baselines. Mitigation: compare under equal imported simulation counts.
- **Multiple comparisons:** many ablations and methods can create cherry-picked claims. Mitigation: report all methods and all seeds, not only winners.
- **Metric leakage:** result-derived columns must not leak into pre-simulation selection. Mitigation: reuse forbidden leakage columns and add validation checks when building scenarios.
- **Overclaiming:** simulation evidence is not physical validation. Mitigation: boundary audit plus explicit report wording.

Recommended claim language after Phase 3:

```text
Under the configured simulation-only benchmark protocol, PIA-CA-LLSO improved
budget-to-target and/or best simulated score relative to the tested baselines.
These results are simulation-only evidence and do not constitute physical
validation.
```
