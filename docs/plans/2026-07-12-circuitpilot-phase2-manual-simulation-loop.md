# CircuitPilot Phase 2 Manual Simulation Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a trustworthy, resumable candidate-approval and manual-simulation loop on top of the accepted Phase 1 product kernel.

**Architecture:** Keep candidate generation and simulation contracts in the existing domain kernel. Add product persistence and services for comparisons, experiments, candidates and simulation jobs; expose them through `/api/v1`; then add an Evidence Cockpit workflow that never labels a candidate improved before matching imported simulation evidence is evaluated.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, existing `goa_eval` optimizers and `pia_ca_llso.simulation_contract`, React 19, TypeScript, Vite, Vitest, pytest, Playwright.

---

## Delivery rules

- Start from `origin/main` after Phase 1 acceptance; use a dedicated `codex/product-phase2-manual-loop` worktree.
- Invoke `@test-driven-development` for every behavior change and `@frontend-skill` for Task 6.
- Keep algorithms in existing optimizer modules; Phase 2 adds orchestration, state, evidence gates and UI.
- Persist metadata and bounded JSON only in SQLite. Keep netlists, batches, imported results and logs in `LocalArtifactStore`.
- Never execute a simulator automatically in Phase 2.
- Preserve exactly:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

- Selection score and evaluated score are separate fields.
- A candidate may become `confirmed_improvement` only after a result DesignVersion is analyzed and `ComparisonService` validates matching evidence.
- Every import and retry must be idempotent and auditable.
- Use one focused commit per task and stop after each batch checkpoint for review.

## State flow

```text
Experiment(draft)
  → Candidate(proposed → approved/rejected)
  → SimulationJob(draft → exported → waiting_for_results)
  → import(validating → completed/failed)
  → result DesignVersion
  → AnalysisRun
  → Comparison(evidence_insufficient/improved/regressed/neutral)
  → Candidate(evaluated → confirmed_improvement/regressed/neutral)
```

## Batch A — persistence and evidence truth

### Task 1: Add comparison, experiment, candidate and simulation-job persistence

**Files:**

- Modify: `src/goa_eval/product/models.py`
- Modify: `src/goa_eval/product/orm.py`
- Modify: `src/goa_eval/product/repositories.py`
- Modify: `src/goa_eval/product/state_machine.py`
- Create: `alembic/versions/20260712_02_phase2_manual_loop.py`
- Create: `tests/test_product_phase2_repository.py`
- Modify: `tests/test_product_state_machine.py`

**Step 1: Write failing repository round-trip tests**

Add tests for `ComparisonRecord`, `OptimizationExperimentRecord`, `CandidateRecord` and `SimulationJobRecord`. Assert foreign keys, UTC timestamps, stable prefixed IDs and bounded JSON fields round-trip without artifact bytes.

**Step 2: Run RED**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_phase2_repository.py tests/test_product_state_machine.py -q
```

Expected: failure because Phase 2 tables and repository methods do not exist.

**Step 3: Add domain fields and legal transitions**

Required candidate fields:

```python
parent_version_id: str
parameter_changes: dict[str, object]
strategy: str
reason_codes: list[str]
selection_score: float | None
evaluated_score: float | None
must_resimulate: bool
```

Required job identity fields:

```python
adapter_type: str
export_attempt: int
import_attempt: int
batch_ref: ArtifactRef | None
result_ref: ArtifactRef | None
result_sha256: str | None
error_code: str | None
retryable: bool
```

Reject direct `proposed → confirmed_improvement` and `approved → confirmed_improvement` transitions.

**Step 4: Add ORM tables and migration**

Create `comparisons`, `optimization_experiments`, `candidates` and `simulation_jobs`. Add uniqueness for `(simulation_job_id, result_sha256)` and indexes for project, experiment, candidate and status queries.

**Step 5: Implement repository methods**

```python
add_comparison(record)
get_comparison(comparison_id)
list_comparisons(project_id)
add_experiment(record)
update_experiment(record)
get_experiment(experiment_id)
add_candidate(record)
update_candidate(record)
get_candidate(candidate_id)
list_candidates(experiment_id)
add_simulation_job(record)
update_simulation_job(record)
get_simulation_job(job_id)
list_simulation_jobs(project_id)
```

**Step 6: Verify migration and commit**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_phase2_repository.py tests/test_product_state_machine.py tests/test_product_repository.py -q
python -m ruff check src/goa_eval/product tests/test_product_phase2_repository.py
git diff --check
git add src/goa_eval/product alembic/versions/20260712_02_phase2_manual_loop.py tests/test_product_phase2_repository.py tests/test_product_state_machine.py
git commit -m "feat(product): persist phase2 workflow state"
```

### Task 2: Add evaluated comparison and claim gating

**Files:**

- Create: `src/goa_eval/product/comparison_service.py`
- Create: `tests/test_product_comparison_service.py`
- Modify: `src/goa_eval/product/evidence_service.py`
- Modify: `tests/test_product_evidence_service.py`

**Step 1: Write failing verdict tests**

Cover `improved`, `regressed`, `neutral` and `evidence_insufficient`. Require matching baseline/result AnalysisRuns, metric artifacts and evidence boundaries. A high selection score without a result AnalysisRun must return `evidence_insufficient`.

**Step 2: Run RED**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_comparison_service.py tests/test_product_evidence_service.py -q
```

**Step 3: Implement `ComparisonService`**

```python
compare_versions(
    project_id,
    baseline_version_id,
    result_version_id,
    baseline_run_id,
    result_run_id,
) -> ComparisonRecord
```

Read evaluated `real_summary.json`, `score_summary.json` and metric tables from artifact references. Store metric deltas, constraint transitions, evidence IDs and the verdict. Do not read `selection_score` when computing the verdict.

**Step 4: Implement confirmation gate**

```python
confirm_candidate(candidate_id, comparison_id) -> CandidateRecord
```

Allow confirmation only when the comparison is `improved`, both runs are complete, boundaries match, and imported result provenance names the same candidate and simulation job.

**Step 5: Verify and commit**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_comparison_service.py tests/test_product_evidence_service.py tests/test_multi_agent_optimization_loop.py -q
python -m ruff check src/goa_eval/product/comparison_service.py tests/test_product_comparison_service.py
git diff --check
git add src/goa_eval/product/comparison_service.py src/goa_eval/product/evidence_service.py tests/test_product_comparison_service.py tests/test_product_evidence_service.py
git commit -m "feat(product): gate claims on evaluated comparisons"
```

**Batch A checkpoint**

Run all product model, repository, state-machine and evidence tests. Review the migration before continuing.

## Batch B — experiments and resumable manual simulation

### Task 3: Add experiment and explicit candidate approval service

**Files:**

- Create: `src/goa_eval/product/experiment_service.py`
- Create: `tests/test_product_experiment_service.py`
- Modify: `src/goa_eval/product/models.py`

**Step 1: Write failing lifecycle tests**

Cover create, deterministic generation, approve, reject, repeated approve, illegal status and audit actor. Every candidate must retain its parent version, parameter changes, strategy, reason codes and `must_resimulate=True`.

**Step 2: Run RED**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_experiment_service.py -q
```

**Step 3: Implement service using existing optimizers**

```python
create_experiment(project_id, baseline_version_id, strategy_config)
generate_candidates(experiment_id, strategy, max_candidates, seed)
approve_candidate(candidate_id, actor_id)
reject_candidate(candidate_id, actor_id, reason)
resume_experiment(experiment_id)
```

Dispatch to existing rule, hybrid or PIA wrapper entrypoints. Do not copy scoring or acquisition logic. Repeating generation with the same experiment, seed and config must return the persisted candidate set.

**Step 4: Verify and commit**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_experiment_service.py tests/test_goa_hybrid_optimizer.py tests/test_pia_acquisition.py -q
python -m ruff check src/goa_eval/product/experiment_service.py tests/test_product_experiment_service.py
git diff --check
git add src/goa_eval/product/experiment_service.py src/goa_eval/product/models.py tests/test_product_experiment_service.py
git commit -m "feat(product): manage candidate approval"
```

### Task 4: Add resumable manual simulation export and import

**Files:**

- Create: `src/goa_eval/product/simulation_job_service.py`
- Create: `tests/test_product_simulation_job_service.py`
- Modify: `src/goa_eval/product/artifact_store.py` only if atomic failed-import quarantine is missing
- Modify: `src/goa_eval/product/project_service.py`

**Step 1: Write failing export tests**

Approved candidates produce a batch through the existing `build_simulation_batch` contract. Proposed/rejected candidates are refused. Repeated export returns the same persisted batch unless an explicit new attempt is requested.

**Step 2: Write failing import and resume tests**

Reject unknown candidate IDs, duplicates, missing columns, cross-job results, path traversal, mismatched parameter hashes and fake evidence upgrades. A process restart must resume from persisted job status without re-creating candidates or batches.

**Step 3: Run RED**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_simulation_job_service.py tests/test_pia_simulation_contract.py -q
```

**Step 4: Implement service**

```python
create_manual_job(candidate_ids, adapter_type="manual")
export_job(job_id, force_new_attempt=False)
preview_import(job_id, result_path)
commit_import(job_id, manifest_sha256)
retry_job(job_id)
```

`preview_import` validates and writes a quarantined immutable artifact. `commit_import` must require the preview manifest hash, publish the accepted result atomically, create a result DesignVersion, and preserve failed artifacts for audit.

**Step 5: Add crash-safe idempotency**

- Derive an import key from job ID plus result SHA-256.
- Return the prior successful result for a repeated identical import.
- Refuse different bytes under an already committed attempt.
- Append an audit event for create, export, preview, commit, failure and retry.

**Step 6: Verify and commit**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_simulation_job_service.py tests/test_pia_simulation_contract.py tests/test_product_artifact_store.py tests/test_product_project_service.py -q
python -m ruff check src/goa_eval/product/simulation_job_service.py tests/test_product_simulation_job_service.py
git diff --check
git add src/goa_eval/product/simulation_job_service.py src/goa_eval/product/artifact_store.py src/goa_eval/product/project_service.py tests/test_product_simulation_job_service.py
git commit -m "feat(product): add resumable manual simulation jobs"
```

Only stage files that changed.

**Batch B checkpoint**

Restart the test container between export and import, then prove the job resumes from SQLite and Artifact Store without duplicate records.

## Batch C — API and Evidence Cockpit workflow

### Task 5: Expose Phase 2 Product API contracts

**Files:**

- Modify: `src/goa_eval/product_api/schemas.py`
- Modify: `src/goa_eval/product_api/dependencies.py`
- Modify: `src/goa_eval/product_api/app.py`
- Create: `src/goa_eval/product_api/routes/experiments.py`
- Create: `src/goa_eval/product_api/routes/simulation_jobs.py`
- Create: `src/goa_eval/product_api/routes/comparisons.py`
- Modify: `src/goa_eval/product_api/routes/__init__.py`
- Create: `tests/test_product_phase2_api.py`

**Step 1: Write failing API contract tests**

Cover experiment create/generate, approve/reject, job create/export, import preview/commit/retry, comparison create/get and candidate confirmation.

**Step 2: Require stable errors**

Use `409` for illegal transitions, `422` for invalid result contracts, `413` for oversized uploads and `404` for unknown resources. Responses must preserve `error_code`, `details`, `retryable` and `artifact_refs` without absolute paths or tracebacks.

**Step 3: Implement routes**

```text
POST /api/v1/projects/{project_id}/experiments
POST /api/v1/experiments/{experiment_id}/candidates:generate
POST /api/v1/candidates/{candidate_id}:approve
POST /api/v1/candidates/{candidate_id}:reject
POST /api/v1/simulation-jobs
POST /api/v1/simulation-jobs/{job_id}:export
POST /api/v1/simulation-jobs/{job_id}/imports:preview
POST /api/v1/simulation-jobs/{job_id}/imports:commit
POST /api/v1/simulation-jobs/{job_id}:retry
POST /api/v1/comparisons
GET  /api/v1/comparisons/{comparison_id}
POST /api/v1/candidates/{candidate_id}:confirm
```

**Step 4: Verify and commit**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_phase2_api.py tests/test_product_api.py tests/test_web_api.py -q
python -m ruff check src/goa_eval/product_api tests/test_product_phase2_api.py
git diff --check
git add src/goa_eval/product_api tests/test_product_phase2_api.py
git commit -m "feat(product): expose manual simulation loop API"
```

### Task 6: Add experiment, simulation job and comparison pages

**Required skills:** `@frontend-skill`, `@test-driven-development`, then `@playwright` for browser acceptance.

**Files:**

- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/api/productClient.ts`
- Modify: `frontend/src/types/product.ts`
- Create: `frontend/src/pages/ExperimentPage.tsx`
- Create: `frontend/src/pages/SimulationJobPage.tsx`
- Create: `frontend/src/pages/ComparisonPage.tsx`
- Create: `frontend/src/components/optimization/CandidateApprovalTable.tsx`
- Create: `frontend/src/components/optimization/ExperimentTimeline.tsx`
- Create: `frontend/src/components/optimization/SimulationImportPanel.tsx`
- Create: `frontend/src/pages/ExperimentPage.test.tsx`
- Create: `frontend/src/pages/SimulationJobPage.test.tsx`
- Create: `frontend/src/pages/ComparisonPage.test.tsx`
- Modify: `frontend/src/router.test.tsx`
- Modify: `frontend/src/api/productClient.test.ts`

**Step 1: Write failing route and client tests**

Add `/experiments/:experimentId`, `/simulation-jobs/:jobId` and `/comparisons/:comparisonId`. Preserve structured API errors and artifact references.

**Step 2: Write failing state tests**

Cover explicit approval, rejection, export eligibility, import preview warning, import failure with retained file, retry after reload, comparison loading and evidence-insufficient verdict.

**Step 3: Implement UI using existing components**

Reuse `CandidateRankingTable` and `BeforeAfterPanel` through adapters. Every candidate row shows `must_resimulate`. Never render “confirmed improvement” from selection score or imported bytes alone.

**Step 4: Preserve Evidence Cockpit design**

Use the existing cyan primary action, amber evidence warning, emerald evaluated confirmation and red failure tokens. Keep one primary action per state, clear focus, contained table scrolling and mobile vertical flow.

**Step 5: Verify and commit**

```powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
git diff --check
git add frontend/src
git commit -m "feat(frontend): add manual simulation workspace"
```

**Batch C checkpoint**

Review API payloads and all three pages before end-to-end integration.

## Task 7: Phase 2 end-to-end acceptance and release record

**Files:**

- Create: `tests/test_product_phase2_e2e.py`
- Create: `docs/plans/2026-07-12-circuitpilot-phase2-acceptance.md`
- Modify: `.github/workflows/ci.yml` only if a focused Phase 2 test command must be added

**Step 1: Write the failing deterministic story test**

The fixture must create a Project and baseline, analyze it, generate and approve a candidate, export a manual batch, restart services, import a matching deterministic result, create/analyze the result DesignVersion, compare it and confirm the candidate.

**Step 2: Assert evidence boundaries at every transition**

Before comparison, assert the UI/API never reports `confirmed_improvement`. After comparison, require matching candidate ID, job ID, result SHA-256, evaluated artifacts and exact evidence boundary.

**Step 3: Run full verification**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_*.py tests/test_web_api.py tests/test_dashboard_api.py tests/test_product_demo_workflow.py -q
python -m pytest -q
python -m ruff check src tests
Set-Location frontend
npm test
npm run build
Set-Location ..
git diff --check
```

**Step 4: Run Playwright acceptance**

At 1440×900, 1024×768 and 390×844 verify the complete story, reload recovery, long IDs/file names, visible focus, no page overflow and no premature improvement claim. Keep screenshots temporary.

**Step 5: Audit forbidden artifacts**

Do not commit databases, uploaded results, waveforms, netlists, screenshots, Playwright output, `node_modules` or simulator binaries.

**Step 6: Write acceptance record and commit**

```powershell
git add tests/test_product_phase2_e2e.py docs/plans/2026-07-12-circuitpilot-phase2-acceptance.md .github/workflows/ci.yml
git commit -m "test(product): verify phase2 manual simulation loop"
```

Only stage the workflow if it changed.

## Completion criteria

- Candidate approval is explicit and audited.
- Manual export uses the existing simulation contract.
- Import is previewed, validated, idempotent and resumable after restart.
- Result artifacts are immutable and path-safe.
- Result DesignVersion and AnalysisRun are linked to candidate and job provenance.
- Comparison uses evaluated artifacts, never selection score.
- `confirmed_improvement` is impossible before a valid improved comparison.
- Legacy CLI, Demo, Dashboard and Phase 1 upload remain compatible.
- Full Python, Ruff, frontend tests/build and three-viewport Playwright acceptance pass.
- No simulator is automatically executed in Phase 2.
