# CircuitPilot Route C Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a GOA-first, profile-extensible CircuitPilot product on top of the existing goa_eval analysis, optimization, simulation-contract, evidence, and product-demo kernel.

**Architecture:** Keep the current evaluators and optimizers as the domain kernel. Add a modular product application layer, a versioned /api/v1 FastAPI surface, SQLite metadata storage, file/object artifact storage, and a routed React workspace. Preserve the current upload-analysis and read-only dashboard APIs during migration.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, pandas, existing goa_eval modules, React 19, TypeScript, Vite, Vitest, Testing Library, pytest.

---

## Execution rules

- Execute in a dedicated codex/ worktree; do not implement directly in the current dirty worktree.
- Keep changes additive under the existing goa_eval package.
- Preserve all existing CLI commands, public demo artifacts and API entrypoints.
- Use TDD for every task: failing test, minimal implementation, passing test, focused commit.
- Before every commit run git diff --check and the focused tests.
- Before each phase completes, run its regression set.
- On Windows PowerShell, set PYTHONPATH to src if Python resolves an installed package.
- Do not stage .trae/, private waveforms, local databases, generated outputs or unrelated dirty files.
- Preserve these values exactly in database summaries, APIs, UI, reports and artifact bundles:

~~~text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
~~~

## Delivery map

| Phase | Product outcome | Tasks |
|---|---|---|
| 0 | Product domain and storage kernel | 1-4 |
| 1 | Complete GOA analysis workspace | 5-9 |
| 2 | Candidate approval and manual simulation loop | 10-13 |
| 3 | PIA and controlled simulator execution | 14-16 |
| 4 | General profiles and release verification | 17-19 |

---

## Phase 0: Product domain and storage kernel

### Task 1: Add product settings and dependencies

**Files:**

- Modify: pyproject.toml
- Create: src/goa_eval/product/__init__.py
- Create: src/goa_eval/product/settings.py
- Test: tests/test_product_settings.py

**Step 1: Write the failing test**

~~~python
from pathlib import Path

from goa_eval.product.settings import ProductSettings


def test_product_settings_use_safe_local_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = ProductSettings.from_env()
    assert settings.database_url == "sqlite:///outputs/product/circuitpilot.db"
    assert settings.artifact_root == Path("outputs/product/artifacts")
    assert settings.job_execution_enabled is False
~~~

**Step 2: Run the test and verify failure**

Run:

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_settings.py -q
~~~

Expected: FAIL because goa_eval.product.settings does not exist.

**Step 3: Add dependencies**

Add SQLAlchemy 2 and Alembic to project dependencies. Do not add a production queue yet.

**Step 4: Implement settings**

Implement a frozen ProductSettings dataclass with database_url, artifact_root and job_execution_enabled. Read CIRCUITPILOT_DATABASE_URL, CIRCUITPILOT_ARTIFACT_ROOT and CIRCUITPILOT_JOB_EXECUTION_ENABLED. Automatic external command execution must default to false.

**Step 5: Run the focused test**

Expected: PASS.

**Step 6: Commit**

~~~powershell
git add pyproject.toml src/goa_eval/product tests/test_product_settings.py
git commit -m "feat: add CircuitPilot product settings"
~~~

### Task 2: Define domain records and legal states

**Files:**

- Create: src/goa_eval/product/models.py
- Create: src/goa_eval/product/state_machine.py
- Test: tests/test_product_models.py
- Test: tests/test_product_state_machine.py

**Step 1: Write failing model tests**

~~~python
from goa_eval.product.models import CandidateStatus, EvidenceBoundary, new_id


def test_default_candidate_boundary_requires_resimulation():
    boundary = EvidenceBoundary()
    assert boundary.data_source == "real_simulation_csv"
    assert boundary.engineering_validity == "simulation_only"
    assert boundary.must_resimulate is True


def test_new_ids_include_resource_prefix():
    assert new_id("project").startswith("project_")


def test_proposal_is_not_confirmed_improvement():
    assert CandidateStatus.PROPOSED != CandidateStatus.CONFIRMED_IMPROVEMENT
~~~

**Step 2: Write failing transition tests**

~~~python
import pytest

from goa_eval.product.models import CandidateStatus
from goa_eval.product.state_machine import InvalidTransition, transition_candidate


def test_candidate_can_be_approved():
    assert transition_candidate(
        CandidateStatus.PROPOSED,
        CandidateStatus.APPROVED,
    ) == CandidateStatus.APPROVED


def test_candidate_cannot_skip_resimulation():
    with pytest.raises(InvalidTransition):
        transition_candidate(
            CandidateStatus.PROPOSED,
            CandidateStatus.CONFIRMED_IMPROVEMENT,
        )
~~~

**Step 3: Implement records**

Add string enums for AnalysisStatus, CandidateStatus, ExperimentStatus and SimulationJobStatus. Add frozen dataclasses for EvidenceBoundary, WorkspaceRecord, ProjectRecord, DesignVersionRecord, AnalysisRunRecord, EvidenceRecord, OptimizationExperimentRecord, CandidateRecord and SimulationJobRecord.

Construct EvidenceBoundary defaults from product_demo.schemas.default_evidence_boundary rather than copying literals.

**Step 4: Implement transition tables**

Provide transition_analysis, transition_candidate, transition_experiment and transition_simulation_job. Illegal transitions raise InvalidTransition with resource, current and requested fields.

Required rules:

- failed analysis cannot become completed;
- proposed candidate cannot become confirmed improvement;
- only evaluated resimulation may become improved, regressed or neutral;
- paused or waiting experiments may resume;
- failed jobs retry through an explicit transition.

**Step 5: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_models.py tests/test_product_state_machine.py -q
git add src/goa_eval/product/models.py src/goa_eval/product/state_machine.py tests/test_product_models.py tests/test_product_state_machine.py
git commit -m "feat: define product domain workflow"
~~~

### Task 3: Add SQLite repository and migrations

**Files:**

- Create: src/goa_eval/product/database.py
- Create: src/goa_eval/product/orm.py
- Create: src/goa_eval/product/repositories.py
- Create: alembic.ini
- Create: alembic/env.py
- Create: alembic/versions/20260711_01_product_core.py
- Test: tests/test_product_repository.py

**Step 1: Write a failing round-trip test**

~~~python
from goa_eval.product.database import create_schema, make_engine
from goa_eval.product.models import ProjectRecord, new_id
from goa_eval.product.repositories import SqlAlchemyProductRepository


def test_project_round_trip(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'product.db'}")
    create_schema(engine)
    repo = SqlAlchemyProductRepository(engine)
    project = ProjectRecord(
        project_id=new_id("project"),
        workspace_id="workspace_default",
        name="720-stage GOA",
        circuit_profile_id="goa_8k_reference",
        spec_revision_id="spec_v1",
    )
    repo.add_project(project)
    assert repo.get_project(project.project_id) == project
~~~

**Step 2: Verify failure**

Expected: FAIL because repository modules do not exist.

**Step 3: Implement ORM tables**

Create workspaces, projects, design_versions, analysis_runs, evidence_records and audit_events. Use prefixed string IDs, UTC timestamps, foreign keys and JSON only for small structured metadata. Never store waveform bytes in SQLite.

**Step 4: Implement repository interface**

Required operations:

~~~python
add_workspace(record)
add_project(record)
get_project(project_id)
list_projects(workspace_id)
add_design_version(record)
get_design_version(version_id)
add_analysis_run(record)
update_analysis_run(record)
get_analysis_run(run_id)
add_evidence(record)
list_evidence(subject_type, subject_id)
append_audit_event(event)
~~~

Return domain records rather than ORM objects.

**Step 5: Add migration smoke coverage**

Upgrade a temporary SQLite database and assert all six tables exist.

**Step 6: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_repository.py -q
git add alembic.ini alembic src/goa_eval/product/database.py src/goa_eval/product/orm.py src/goa_eval/product/repositories.py tests/test_product_repository.py
git commit -m "feat: persist CircuitPilot product metadata"
~~~

### Task 4: Add safe artifact storage

**Files:**

- Create: src/goa_eval/product/artifact_store.py
- Test: tests/test_product_artifact_store.py

**Step 1: Write failing tests**

Verify that LocalArtifactStore:

- writes under the configured root;
- returns URI, size and SHA-256;
- rejects ../escape.csv and absolute paths;
- publishes directories only after validation;
- resolves only references inside its root;
- never deletes unrelated directories.

Example:

~~~python
ref = store.put_bytes(
    "workspace_a/project_a/inputs/input_a/waveform.csv",
    b"t,v\n0,0\n",
)
assert ref.uri.endswith("waveform.csv")
assert len(ref.sha256) == 64
~~~

**Step 2: Implement ArtifactStore protocol**

Required methods:

~~~python
put_bytes(key, data)
put_file(key, source)
publish_directory(prefix, source)
resolve(ref)
exists(ref)
~~~

Reuse the containment pattern in src/goa_eval/web/storage.py, but raise domain exceptions rather than FastAPI exceptions.

**Step 3: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_artifact_store.py -q
git add src/goa_eval/product/artifact_store.py tests/test_product_artifact_store.py
git commit -m "feat: add product artifact storage"
~~~

**Phase 0 checkpoint**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_settings.py tests/test_product_models.py tests/test_product_state_machine.py tests/test_product_repository.py tests/test_product_artifact_store.py -q
git diff --check
~~~

Expected: all focused tests pass.

---

## Phase 1: Complete GOA analysis workspace

### Task 5: Add project and design-version service

**Files:**

- Create: src/goa_eval/product/project_service.py
- Test: tests/test_product_project_service.py

**Step 1: Write failing tests**

Cover:

- default workspace creation;
- GOA project creation;
- frozen circuit-profile and spec revision references;
- baseline design version creation;
- rejection of unknown profiles using existing resolve_circuit_profile.

**Step 2: Implement ProjectService**

Public methods:

~~~python
create_workspace(name)
create_project(workspace_id, name, circuit_profile_id, spec_revision_id)
create_design_version(
    project_id,
    label,
    parameter_set_ref,
    netlist_ref,
    parent_version_id=None,
)
get_project_overview(project_id)
~~~

The overview returns counts and latest states but not large artifact contents.

**Step 3: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_project_service.py tests/test_circuit_profiles.py -q
git add src/goa_eval/product/project_service.py tests/test_product_project_service.py
git commit -m "feat: manage product projects and versions"
~~~

### Task 6: Extract shared analysis orchestration

**Files:**

- Create: src/goa_eval/product/analysis_service.py
- Modify: src/goa_eval/web/runners.py
- Test: tests/test_product_analysis_service.py
- Modify test: tests/test_web_api.py

**Step 1: Write a failing parity test**

Run examples/sample_waveform.csv and examples/sample_params.yaml through the new service. Assert:

~~~python
assert result.status == "completed"
assert result.boundary["data_source"] == "real_simulation_csv"
assert result.boundary["engineering_validity"] == "simulation_only"
assert result.boundary["must_resimulate"] is True
assert (result.analysis_dir / "real_summary.json").exists()
assert (result.bundle_dir / "06_dashboard_data/dashboard_summary.json").exists()
~~~

**Step 2: Implement AnalysisService**

Add run_analysis with explicit inputs for analysis record, input directory, output directory, profile, topology, stage count, node pattern, candidate flag and LLM flag.

It must call the existing:

- run_real_waveform_evaluation;
- recommendation builder;
- constrained candidate generator;
- run_product_demo.

Do not copy metric, scorer or candidate algorithms.

**Step 3: Convert web/runners.py into a compatibility adapter**

Translate UploadedCaseConfig to the service request and translate the result back to CaseRunResult. Keep /api/cases, /api/cases/preview and /api/demo/sample-case behavior unchanged.

**Step 4: Run parity tests**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_analysis_service.py tests/test_web_api.py tests/test_product_demo_workflow.py -q
~~~

Expected: new and legacy tests pass.

**Step 5: Commit**

~~~powershell
git add src/goa_eval/product/analysis_service.py src/goa_eval/web/runners.py tests/test_product_analysis_service.py tests/test_web_api.py
git commit -m "refactor: share product analysis orchestration"
~~~

### Task 7: Structure issues and evidence records

**Files:**

- Create: src/goa_eval/product/issue_service.py
- Create: src/goa_eval/product/evidence_service.py
- Test: tests/test_product_issue_service.py
- Test: tests/test_product_evidence_service.py

**Step 1: Write issue tests**

Given a score with FAIL_RIPPLE, require one issue containing severity, affected metric, possible causes, recommended actions and evidence references. Unknown failure keys must produce an unclassified issue rather than disappearing.

**Step 2: Write evidence tests**

Verify:

- normalize_evidence_boundary is the normalization source;
- artifact hashes become EvidenceRecord rows;
- mock evidence cannot become reportable_as_real_ngspice;
- missing required evidence produces evidence_incomplete;
- unresimulated candidates cannot be confirmed.

**Step 3: Implement services**

IssueService maps existing score, diagnosis and recommendation artifacts into structured issue records. Existing Markdown remains downloadable.

EvidenceService exposes:

~~~python
index_analysis_artifacts(run_id, artifact_refs, raw_evidence)
validate_boundary(evidence)
can_confirm_improvement(candidate, result_run)
~~~

**Step 4: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_issue_service.py tests/test_product_evidence_service.py tests/test_evidence_level.py -q
git add src/goa_eval/product/issue_service.py src/goa_eval/product/evidence_service.py tests/test_product_issue_service.py tests/test_product_evidence_service.py
git commit -m "feat: structure analysis issues and evidence"
~~~

### Task 8: Add the versioned product API

**Files:**

- Create: src/goa_eval/product_api/__init__.py
- Create: src/goa_eval/product_api/schemas.py
- Create: src/goa_eval/product_api/dependencies.py
- Create: src/goa_eval/product_api/app.py
- Test: tests/test_product_api.py

**Step 1: Write failing API tests**

Using FastAPI TestClient, verify:

- POST /api/v1/workspaces returns 201;
- POST /api/v1/projects creates a GOA project;
- POST /api/v1/projects/{id}/design-versions creates a baseline;
- POST /api/v1/design-versions/{id}/analysis-runs starts analysis;
- GET /api/v1/projects/{id}/overview returns stable empty states;
- unknown resources return a stable error_code;
- responses containing evidence include all three boundary fields.

**Step 2: Implement DTOs**

Keep Pydantic API DTOs separate from ORM and domain records. Every top-level response includes schema_version = 1.0.

**Step 3: Implement dependency container**

ProductContainer owns settings, engine, repository, artifact store and services. Tests inject temporary components; production paths must not leak into tests.

**Step 4: Implement only Phase 1 routes**

Do not add candidate or simulator routes in this task.

**Step 5: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_api.py -q
git add src/goa_eval/product_api tests/test_product_api.py
git commit -m "feat: add versioned CircuitPilot product API"
~~~

### Task 9: Add routed frontend and GOA analysis pages

**Files:**

- Modify: frontend/package.json
- Modify: frontend/package-lock.json
- Modify: frontend/src/App.tsx
- Create: frontend/src/router.tsx
- Create: frontend/src/layouts/ProductShell.tsx
- Create: frontend/src/api/productClient.ts
- Create: frontend/src/types/product.ts
- Create: frontend/src/pages/ProjectListPage.tsx
- Create: frontend/src/pages/NewProjectPage.tsx
- Create: frontend/src/pages/ProjectOverviewPage.tsx
- Create: frontend/src/pages/DesignVersionPage.tsx
- Create: frontend/src/pages/AnalysisRunPage.tsx
- Create: frontend/src/components/analysis/IssueList.tsx
- Test: frontend/src/router.test.tsx
- Test: frontend/src/pages/AnalysisRunPage.test.tsx
- Modify test: frontend/src/App.test.tsx

**Step 1: Add React Router**

Run npm install react-router-dom under frontend and review the lockfile.

**Step 2: Write route tests**

Verify project list, project overview and analysis routes. Keep the current demo/case path readable during migration.

**Step 3: Write analysis-page tests**

The page must distinguish:

- preview ready;
- analysis running;
- analysis complete;
- hard-constraint failure;
- evidence incomplete;
- resource loading failure.

**Step 4: Implement the product client**

Preserve error_code, retryable, details and artifact_refs. Do not collapse server errors to one string.

**Step 5: Reuse current components**

Compose OverviewCards, EvidenceBoundaryCard, ConstraintStatusPanel, FiguresGallery and ReportsPanel. Do not duplicate dashboard presentation code.

**Step 6: Run and commit**

~~~powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
git add frontend
git commit -m "feat: add GOA analysis workspace"
~~~

**Phase 1 checkpoint**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_*.py tests/test_web_api.py tests/test_dashboard_api.py tests/test_product_demo_workflow.py tests/test_circuit_profiles.py -q
Set-Location frontend
npm test
npm run build
Set-Location ..
git diff --check
~~~

Manually verify that the old upload demo and the new product workspace show the same summary and evidence for the public sample.

---

## Phase 2: Candidate approval and manual simulation loop

### Task 10: Add version comparison and claim gating

**Files:**

- Modify: src/goa_eval/product/models.py
- Modify: src/goa_eval/product/orm.py
- Modify: src/goa_eval/product/repositories.py
- Create: src/goa_eval/product/comparison_service.py
- Create: alembic/versions/20260711_02_comparisons.py
- Test: tests/test_product_comparison_service.py

**Step 1: Write failing comparison tests**

Cover improved, regressed, neutral and evidence_insufficient. A high selection score without matching resimulation must return evidence_insufficient.

**Step 2: Add comparison persistence**

Store baseline run, result run, metric deltas, constraint changes, verdict and evidence IDs.

**Step 3: Implement ComparisonService**

Read actual real_summary.json, score_summary.json and metric tables. Never compare predicted/selection scores as evaluated results.

**Step 4: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_comparison_service.py tests/test_multi_agent_optimization_loop.py -q
git add src/goa_eval/product alembic/versions/20260711_02_comparisons.py tests/test_product_comparison_service.py
git commit -m "feat: compare evaluated design versions"
~~~

### Task 11: Add experiments and candidate approval

**Files:**

- Modify: src/goa_eval/product/models.py
- Modify: src/goa_eval/product/orm.py
- Modify: src/goa_eval/product/repositories.py
- Create: src/goa_eval/product/experiment_service.py
- Create: alembic/versions/20260711_03_experiments.py
- Modify: src/goa_eval/product_api/schemas.py
- Modify: src/goa_eval/product_api/app.py
- Test: tests/test_product_experiment_service.py
- Modify test: tests/test_product_api.py

**Step 1: Write failing candidate tests**

Every generated candidate must store:

- parent design version;
- parameter changes;
- strategy and reason codes;
- selection score separately from evaluated score;
- approval status;
- must_resimulate = true.

**Step 2: Add experiment and candidate tables**

Use JSON for bounded strategy config and parameter changes. Keep IDs and state transitions explicit.

**Step 3: Implement ExperimentService**

~~~python
create_experiment(...)
generate_candidates(experiment_id, strategy, max_candidates, seed)
approve_candidate(candidate_id, actor_id)
reject_candidate(candidate_id, actor_id, reason)
~~~

Call existing rule, hybrid or PIA wrapper functions. Do not copy algorithms.

**Step 4: Add API routes**

Add create, generate, approve and reject. Illegal transitions return HTTP 409 with EXPERIMENT_STATE_CONFLICT.

**Step 5: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_experiment_service.py tests/test_product_api.py tests/test_cli_smoke.py -q
git add src/goa_eval/product src/goa_eval/product_api alembic/versions/20260711_03_experiments.py tests/test_product_experiment_service.py tests/test_product_api.py
git commit -m "feat: manage optimization experiments"
~~~

### Task 12: Add manual simulation export and result import

**Files:**

- Modify: src/goa_eval/product/models.py
- Modify: src/goa_eval/product/orm.py
- Modify: src/goa_eval/product/repositories.py
- Create: src/goa_eval/product/simulation_job_service.py
- Create: alembic/versions/20260711_04_simulation_jobs.py
- Modify: src/goa_eval/product_api/app.py
- Test: tests/test_product_simulation_job_service.py
- Modify test: tests/test_product_api.py

**Step 1: Write export tests**

Approved candidates produce a simulation batch through existing build_simulation_batch. Proposed or rejected candidates are refused.

**Step 2: Write import tests**

Reject:

- unknown or duplicate candidate IDs;
- missing result columns;
- results assigned to another job;
- fake evidence upgrades;
- partial imports without an explicit partial policy.

**Step 3: Implement SimulationJobService**

~~~python
create_manual_job(candidate_ids, adapter_type="manual")
export_job(job_id)
import_results(job_id, results_path)
retry_job(job_id)
~~~

Reuse pia_ca_llso simulation_contract functions and place product persistence around them.

**Step 4: Add multipart API routes**

Implement create, status, export, result upload and retry. Limit upload size and preserve failed import artifacts separately.

**Step 5: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_simulation_job_service.py tests/test_pia_simulation_contract.py tests/test_product_api.py -q
git add src/goa_eval/product src/goa_eval/product_api alembic/versions/20260711_04_simulation_jobs.py tests/test_product_simulation_job_service.py tests/test_product_api.py
git commit -m "feat: add manual simulation workflow"
~~~

### Task 13: Add experiment, job and comparison pages

**Files:**

- Create: frontend/src/pages/ComparisonPage.tsx
- Create: frontend/src/pages/ExperimentPage.tsx
- Create: frontend/src/pages/SimulationJobPage.tsx
- Create: frontend/src/components/optimization/CandidateApprovalTable.tsx
- Create: frontend/src/components/optimization/ExperimentTimeline.tsx
- Modify: frontend/src/router.tsx
- Modify: frontend/src/api/productClient.ts
- Test: frontend/src/pages/ExperimentPage.test.tsx
- Test: frontend/src/pages/SimulationJobPage.test.tsx

**Step 1: Write failing UI tests**

Verify:

- candidate approval calls the explicit endpoint;
- must_resimulate is visible beside candidate actions;
- rejected candidates cannot be exported;
- imported results do not display improvement before comparison;
- failed jobs show error code, retryability and logs.

**Step 2: Implement pages**

Reuse CandidateRankingTable and BeforeAfterPanel through props instead of copying markup.

**Step 3: Run and commit**

~~~powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
git add frontend/src
git commit -m "feat: add optimization experiment workspace"
~~~

**Phase 2 checkpoint**

Run a manual end-to-end fixture:

1. Create a GOA project and baseline.
2. Analyze baseline.
3. Generate and approve a candidate.
4. Export simulation batch.
5. Import matching deterministic result.
6. Create and analyze the result design version.
7. Compare baseline and result.
8. Confirm the UI never labels improvement before step 7.

---

## Phase 3: PIA and controlled simulator execution

### Task 14: Map PIA evolution into product experiments

**Files:**

- Create: src/goa_eval/product/pia_experiment_adapter.py
- Modify: src/goa_eval/product/experiment_service.py
- Test: tests/test_product_pia_experiment_adapter.py

**Step 1: Write failing mapping tests**

Verify:

- generation numbers map to experiment events;
- selected PIA candidates map to product candidates;
- pending generation maps to waiting_for_simulation;
- resume does not duplicate candidates;
- boundary artifacts remain unchanged.

**Step 2: Implement the adapter**

Wrap existing run_evolution_loop and load_resume_state. Store references to generation artifacts; do not rewrite the PIA file format.

**Step 3: Run PIA regression tests**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_pia_experiment_adapter.py tests/test_pia_evolution_loop.py tests/test_pia_evolution_state.py tests/test_pia_boundary_audit.py -q
~~~

**Step 4: Commit**

~~~powershell
git add src/goa_eval/product/pia_experiment_adapter.py src/goa_eval/product/experiment_service.py tests/test_product_pia_experiment_adapter.py
git commit -m "feat: expose PIA product experiments"
~~~

### Task 15: Add a controlled background runner

**Files:**

- Create: src/goa_eval/product/job_runner.py
- Modify: src/goa_eval/product/simulation_job_service.py
- Test: tests/test_product_job_runner.py

**Step 1: Write runner tests**

Verify:

- execution is refused when job_execution_enabled is false;
- only registered adapters can execute;
- timeout produces SIMULATION_TIMEOUT;
- stdout, stderr and exit code are stored;
- retry increments attempt and preserves logs;
- concurrent claims cannot run the same job twice.

**Step 2: Implement the minimal runner**

Use repository claim/update and subprocess with shell=False and timeout. Command arguments come from registered adapter factories, never raw API strings.

**Step 3: Add deterministic fixture coverage**

Use existing local_simulator only for flow tests and force mock evidence fields.

**Step 4: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_job_runner.py tests/test_pia_simulation_executor.py -q
git add src/goa_eval/product/job_runner.py src/goa_eval/product/simulation_job_service.py tests/test_product_job_runner.py
git commit -m "feat: execute registered simulation jobs"
~~~

### Task 16: Register simulator adapters

**Files:**

- Create: src/goa_eval/product/simulator_registry.py
- Create: src/goa_eval/product/adapters/__init__.py
- Create: src/goa_eval/product/adapters/ngspice_sky130.py
- Create: src/goa_eval/product/adapters/empyrean_offline.py
- Test: tests/test_product_simulator_registry.py
- Test: tests/test_product_ngspice_adapter.py
- Test: tests/test_product_empyrean_adapter.py

**Step 1: Write registry tests**

Unknown adapters fail. Registered adapters expose availability, render, execute/import and evidence metadata without executing during availability checks.

**Step 2: Implement strict ngspice/SKY130 adapter**

Reuse sky130-mainline behavior. Missing ngspice or PDK fails closed. Never fall back to mock when real execution was requested.

**Step 3: Implement Empyrean offline adapter**

Reuse current interface manifest, net mapping and parsers. Support export/import only; keep direct tool execution disabled until a controlled integration exists.

**Step 4: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_simulator_registry.py tests/test_product_ngspice_adapter.py tests/test_product_empyrean_adapter.py tests/test_empyrean_import_cli.py -q
git add src/goa_eval/product/simulator_registry.py src/goa_eval/product/adapters tests/test_product_simulator_registry.py tests/test_product_ngspice_adapter.py tests/test_product_empyrean_adapter.py
git commit -m "feat: register controlled simulator adapters"
~~~

**Phase 3 checkpoint**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests -k pia -q
~~~

Also run one fail-closed test without a configured PDK. Run the optional real-ngspice test only in an explicitly configured environment.

---

## Phase 4: General profiles and release verification

### Task 17: Version circuit profiles and semantics

**Files:**

- Create: src/goa_eval/product/profile_service.py
- Modify: src/goa_eval/circuit_profiles.py
- Modify: src/goa_eval/product_api/app.py
- Test: tests/test_product_profile_service.py
- Modify test: tests/test_circuit_profiles.py

**Step 1: Write failing profile tests**

A profile revision records source hash, semantics hash, supported analyses, required metrics, node rules, units and validation result. Reject unknown semantic tags, duplicate aliases and incompatible required metrics.

**Step 2: Implement ProfileService**

Wrap current loaders and freeze a validated revision snapshot into artifact storage. Do not invent metrics dynamically.

**Step 3: Add read-only API**

Expose list, detail and validate. Delay browser-based profile editing until the schema is stable.

**Step 4: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_profile_service.py tests/test_circuit_profiles.py tests/test_generalized_simulation.py -q
git add src/goa_eval/product/profile_service.py src/goa_eval/circuit_profiles.py src/goa_eval/product_api/app.py tests/test_product_profile_service.py tests/test_circuit_profiles.py
git commit -m "feat: version circuit profiles"
~~~

### Task 18: Add non-GOA reference fixtures

**Files:**

- Modify: config/circuit_profiles.yaml
- Create: examples/product_profiles/ota/
- Create: examples/product_profiles/comparator/
- Create: examples/product_profiles/oscillator/
- Create: tests/test_product_reference_profiles.py

**Step 1: Write failing fixture tests**

For OTA, comparator and oscillator:

- load the profile and sample;
- run existing generalized analysis;
- verify required analyses and units;
- preserve provenance and simulation-only boundary;
- do not fabricate GOA metrics.

**Step 2: Add small public fixtures**

Use deterministic, non-private CSVs and explicit expected summaries.

**Step 3: Run and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_reference_profiles.py tests/test_generalized_simulation.py -q
git add config/circuit_profiles.yaml examples/product_profiles tests/test_product_reference_profiles.py
git commit -m "test: add general circuit profile fixtures"
~~~

### Task 19: Add full-story demo, documentation and release verification

**Files:**

- Create: scripts/build_product_demo.py
- Create: tests/test_product_end_to_end.py
- Create: docs/product_quickstart.md
- Create: docs/product_architecture.md
- Create: docs/product_migration.md
- Modify: README.md

**Step 1: Write the end-to-end test**

Cover:

1. workspace creation;
2. GOA project creation;
3. baseline design creation;
4. upload and preview;
5. analysis;
6. issue and evidence indexing;
7. candidate generation and approval;
8. manual job export;
9. deterministic result import;
10. result analysis and comparison;
11. report generation.

Assert the three boundary values and prove confirmation occurs only after imported evaluation.

**Step 2: Implement the reproducible demo builder**

Accept output-dir and database-url arguments. Tests must write only temporary paths. Default user output may use outputs/product_demo_v1.

**Step 3: Write documentation**

Document local start, old and new API roles, project workflow, simulation boundary, evidence meanings, existing case migration and failure recovery.

**Step 4: Run complete verification**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest -q
python scripts/build_product_demo.py --output-dir tmp/product_demo_v1 --database-url sqlite:///tmp/product_demo_v1.db
Set-Location frontend
npm test
npm run build
Set-Location ..
git diff --check
~~~

Expected:

- full Python suite passes;
- frontend tests and build pass;
- demo produces a project, two evaluated versions, a comparison and an evidence package;
- generated output is not staged.

**Step 5: Commit**

~~~powershell
git add scripts/build_product_demo.py tests/test_product_end_to_end.py docs/product_quickstart.md docs/product_architecture.md docs/product_migration.md README.md
git commit -m "docs: complete CircuitPilot product workflow"
~~~

---

## Final release gate

Before declaring Route C implemented:

1. Run the complete Python suite from the isolated worktree.
2. Run frontend tests and production build.
3. Build the public product demo into a temporary directory.
4. Verify CLI, legacy upload API and product API agree on core summary values.
5. Verify every proposed candidate has must_resimulate=true.
6. Verify mock/local results cannot set reportable_as_real_ngspice=true.
7. Verify invalid result IDs fail without mutating experiment state.
8. Verify pending PIA evolution resumes without duplicate candidates.
9. Verify existing product-demo bundles remain readable.
10. Review the remote-base diff and exclude private data and unrelated files.

## Recommended branch sequence

Implement one phase per integration branch:

~~~text
codex/product-phase0-domain-storage
codex/product-phase1-goa-workspace
codex/product-phase2-manual-closed-loop
codex/product-phase3-pia-simulator
codex/product-phase4-general-profiles
~~~

Phase 0 and Phase 1 form the first complete product slice. Phase 2 adds a trustworthy human-in-the-loop optimization workflow. Phase 3 productizes the existing PIA and simulator contract. Phase 4 proves that the GOA-first architecture is genuinely extensible without replacing the current core.

