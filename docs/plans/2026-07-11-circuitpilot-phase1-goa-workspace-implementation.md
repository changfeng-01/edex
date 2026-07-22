# CircuitPilot Phase 1 GOA Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a complete, visually polished GOA project and analysis workspace on top of the Phase 0 product domain, repository, artifact store, and the existing goa_eval analysis kernel.

**Architecture:** Add product application services and a versioned /api/v1 FastAPI surface while preserving the existing upload and read-only dashboard APIs. Keep analysis synchronous in Phase 1 but persist queued/running/completed states so a durable executor can replace it later. Build a routed React engineering cockpit that reuses existing evidence and analysis components.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, existing goa_eval evaluators, React 19, TypeScript, React Router, Tailwind CSS 4, Vitest, Testing Library, pytest.

---

## Required execution skills and rules

- Execute in a dedicated worktree branched from codex/product-phase0-domain-storage.
- Use @test-driven-development for every behavior change.
- Use @executing-plans with review checkpoints after Tasks 1-3, 4-6, and 7-8.
- Task 8 must use @frontend-skill before frontend implementation.
- Task 8 browser verification must use @playwright or the available equivalent browser-verification skill.
- Use @verification-before-completion before claiming any task or phase passes.
- Keep every task in a separate commit.
- Do not modify algorithms in waveform_io, metrics, scorer, diagnosis, recommendation or PIA.
- Preserve all existing CLI commands and old API response shapes.
- Do not commit generated databases, uploads, screenshots, tmp output, private waveforms or node_modules.
- Use PYTHONPATH=src on Windows if the wrong installed package is resolved.
- Preserve these exact values:

~~~text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
~~~

## Batch map

| Batch | Tasks | Review outcome |
|---|---|---|
| A | 1-3 | Projects and immutable input snapshots |
| B | 4-6 | Shared analysis, compatibility, issues and evidence |
| C | 7-8 | Product API and polished React workspace |

---

## Task 1: Extend product repository queries

**Files:**

- Modify: src/goa_eval/product/repositories.py
- Test: tests/test_product_repository_queries.py

**Step 1: Write failing workspace query tests**

~~~python
def test_workspace_round_trip_and_listing(product_repo):
    first = WorkspaceRecord(workspace_id="workspace_a", name="A")
    second = WorkspaceRecord(workspace_id="workspace_b", name="B")
    product_repo.add_workspace(first)
    product_repo.add_workspace(second)

    assert product_repo.get_workspace("workspace_a") == first
    assert product_repo.list_workspaces() == [first, second]
~~~

**Step 2: Run and verify RED**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_repository_queries.py::test_workspace_round_trip_and_listing -q
~~~

Expected: FAIL because get_workspace and list_workspaces do not exist.

**Step 3: Add failing design-version list test**

Create one project with two versions. Assert deterministic created_at/design_version_id ordering and filtering by project.

**Step 4: Add failing analysis query tests**

Verify:

- list_analysis_runs(project_id=...) returns runs across project versions;
- list_analysis_runs(design_version_id=...) filters one version;
- exactly one filter is accepted;
- get_latest_analysis_run returns the newest run;
- unknown project/version returns an empty list rather than another project’s data.

**Step 5: Implement minimal repository methods**

Add:

~~~python
get_workspace(workspace_id)
list_workspaces()
list_design_versions(project_id)
list_analysis_runs(*, project_id=None, design_version_id=None)
get_latest_analysis_run(project_id)
~~~

Use SQL joins for project-level analysis queries. Return domain records, never ORM objects.

**Step 6: Run focused and existing repository tests**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_repository.py tests/test_product_repository_queries.py -q
python -m ruff check src/goa_eval/product/repositories.py tests/test_product_repository_queries.py
git diff --check
~~~

Expected: PASS.

**Step 7: Commit**

~~~powershell
git add src/goa_eval/product/repositories.py tests/test_product_repository_queries.py
git commit -m "feat: query product workspaces and analysis history"
~~~

---

## Task 2: Add ProjectService and immutable configuration snapshots

**Files:**

- Create: src/goa_eval/product/project_service.py
- Modify: src/goa_eval/product/models.py
- Test: tests/test_product_project_service.py

**Step 1: Write failing workspace and project tests**

Use a real temporary SQLite repository and LocalArtifactStore.

Verify:

- create_workspace creates a prefixed ID and audit event;
- create_project refuses an unknown workspace;
- create_project resolves the existing GOA profile;
- unknown profile raises ProductNotFoundError or InvalidCircuitProfile;
- project fields match the request.

**Step 2: Run and verify RED**

Expected: FAIL because ProjectService does not exist.

**Step 3: Write failing snapshot tests**

Inject a temporary profile file and spec file. Assert create_project:

- writes normalized profile_snapshot.json;
- writes spec_snapshot.yaml or normalized JSON;
- records SHA-256 ArtifactRefs;
- creates project EvidenceRecords;
- never stores a mutable source path as the only revision reference;
- keeps data_source and engineering_validity boundaries.

**Step 4: Write failing design-version tests**

Verify:

- baseline version creation;
- unknown project rejection;
- parent version must belong to the same project;
- project overview returns version count, analysis count, latest state and evidence summary;
- overview does not read or return waveform content.

**Step 5: Add domain service errors and result DTOs**

In project_service.py define small domain exceptions and frozen results:

~~~python
@dataclass(frozen=True)
class ProjectCreationResult:
    project: ProjectRecord
    profile_snapshot: ArtifactRef
    spec_snapshot: ArtifactRef
    evidence: tuple[EvidenceRecord, ...]
~~~

Do not import FastAPI.

**Step 6: Implement ProjectService**

Dependencies are injected:

~~~python
ProjectService(
    repository,
    artifact_store,
    circuit_profile_path=Path("config/circuit_profiles.yaml"),
    default_spec_path=Path("config/spec.yaml"),
)
~~~

Methods:

~~~python
create_workspace(name, actor_id="user_local")
create_project(
    workspace_id,
    name,
    circuit_profile_id,
    spec_revision_id,
    spec_path=None,
    actor_id="user_local",
)
create_design_version(...)
get_project_overview(project_id)
~~~

Use resolve_circuit_profile for validation. Normalize mappings before JSON snapshot so hashes are deterministic.

**Step 7: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_project_service.py tests/test_circuit_profiles.py tests/test_product_repository_queries.py -q
python -m ruff check src/goa_eval/product/project_service.py tests/test_product_project_service.py
git diff --check
git add src/goa_eval/product/project_service.py src/goa_eval/product/models.py tests/test_product_project_service.py
git commit -m "feat: manage GOA projects and immutable config snapshots"
~~~

---

## Task 3: Add InputService and immutable Input Snapshots

**Files:**

- Create: src/goa_eval/product/input_service.py
- Modify: src/goa_eval/product/models.py
- Test: tests/test_product_input_service.py

**Step 1: Write failing happy-path test**

Use examples/sample_waveform.csv and examples/sample_params.yaml.

~~~python
result = service.create_input_snapshot(
    design_version_id=version.design_version_id,
    files=[
        InputFile("waveform.csv", waveform_path),
        InputFile("params.yaml", params_path),
    ],
    preview_config=UploadedCaseConfig(case_id="preview"),
)

assert result.preview_status == "preview_ready"
assert result.manifest_ref.uri.startswith("artifact://")
assert result.preview["ready_for_analysis"] is True
~~~

**Step 2: Verify RED**

Expected: FAIL because InputService and InputFile do not exist.

**Step 3: Write failing validation tests**

Verify:

- waveform.csv is mandatory;
- duplicate logical names fail;
- arbitrary absolute client destination paths are not accepted;
- unsupported logical names fail;
- unknown design version fails;
- preview errors do not publish a snapshot;
- source files are not modified;
- image attachments remain display-only;
- warning-only preview becomes preview_ready_with_warnings.

**Step 4: Write failing manifest test**

Resolve manifest_ref and assert:

- input_snapshot_id;
- design_version_id;
- created_at;
- preview_status;
- preview payload;
- logical names;
- Artifact URI;
- size;
- SHA-256;
- exact evidence boundary.

**Step 5: Implement service records**

~~~python
@dataclass(frozen=True)
class InputFile:
    logical_name: str
    source_path: Path

@dataclass(frozen=True)
class InputSnapshotResult:
    input_snapshot_id: str
    design_version_id: str
    preview_status: str
    manifest_ref: ArtifactRef
    preview: dict[str, Any]
~~~

**Step 6: Implement InputService**

Use TemporaryDirectory. Build the existing case_dir/input layout, copy only validated logical files, call inspect_uploaded_case_input, write input_manifest.json, and call LocalArtifactStore.publish_directory once.

If preview fails, return a non-published preview result or raise InputPreviewFailed containing the preview. Do not create AnalysisRun.

**Step 7: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_input_service.py tests/test_input_inspector.py tests/test_product_artifact_store.py -q
python -m ruff check src/goa_eval/product/input_service.py tests/test_product_input_service.py
git diff --check
git add src/goa_eval/product/input_service.py src/goa_eval/product/models.py tests/test_product_input_service.py
git commit -m "feat: create immutable analysis input snapshots"
~~~

**Batch A checkpoint**

Run:

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_repository_queries.py tests/test_product_project_service.py tests/test_product_input_service.py tests/test_product_repository.py tests/test_product_artifact_store.py tests/test_circuit_profiles.py -q
git diff --check
~~~

Report implemented behavior, test counts and commits. Stop for review.

---

## Task 4: Extract shared AnalysisService

**Files:**

- Create: src/goa_eval/product/analysis_service.py
- Create: src/goa_eval/product/pipeline.py
- Modify: src/goa_eval/product/models.py
- Test: tests/test_product_analysis_service.py

**Step 1: Write failing real-sample analysis test**

Create workspace, project, version and Input Snapshot with public examples. Call AnalysisService.

Assert:

~~~python
assert result.status == AnalysisStatus.COMPLETED
assert result.boundary.data_source == "real_simulation_csv"
assert result.boundary.engineering_validity == "simulation_only"
assert result.boundary.must_resimulate is True
assert result.artifact_bundle_ref.uri.startswith("artifact://")
~~~

Resolve the published run bundle and assert real_summary.json, score_summary.json, real_metrics.csv, recommendations.md and product-demo Dashboard files exist.

**Step 2: Verify RED**

Expected: FAIL because AnalysisService does not exist.

**Step 3: Write failing status tests**

Use an injected pipeline callable:

- queued becomes running before pipeline call;
- successful call becomes completed;
- pipeline exception becomes failed;
- missing evidence becomes evidence_incomplete;
- failed run retains a structured error result;
- completed output is published atomically;
- publication failure never leaves completed state.

**Step 4: Write failing read-only suggestion test**

When params exist, next_candidates.csv may be generated, but:

- no CandidateRecord is persisted;
- all suggestions contain must_resimulate=true;
- no confirmed_improvement text appears.

**Step 5: Implement shared pipeline function**

Move the pure orchestration currently inside web/runners.py into:

~~~python
execute_analysis_pipeline(
    input_dir,
    analysis_dir,
    product_demo_root,
    case_id,
    config,
) -> PipelineResult
~~~

It calls existing evaluation, recommendation, optional candidate generation, optional LLM and run_product_demo.

Do not change algorithms.

**Step 6: Implement AnalysisService**

Dependencies:

~~~python
AnalysisService(repository, artifact_store, pipeline=execute_analysis_pipeline)
~~~

Product mode:

1. Resolve Input Snapshot.
2. Create AnalysisRun.
3. Run pipeline in a TemporaryDirectory.
4. Generate run manifest.
5. Publish the complete run directory.
6. Update repository status and Artifact reference.

Provide a compatibility execution option that writes to explicit legacy directories without publishing to product storage. This option is used only by Task 5.

**Step 7: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_analysis_service.py tests/test_real_waveform_eval.py tests/test_product_demo_workflow.py -q
python -m ruff check src/goa_eval/product/analysis_service.py src/goa_eval/product/pipeline.py tests/test_product_analysis_service.py
git diff --check
git add src/goa_eval/product/analysis_service.py src/goa_eval/product/pipeline.py src/goa_eval/product/models.py tests/test_product_analysis_service.py
git commit -m "feat: orchestrate product analysis runs"
~~~

---

## Task 5: Convert the legacy upload runner into a compatibility adapter

**Files:**

- Modify: src/goa_eval/web/runners.py
- Modify: src/goa_eval/web/app.py only if dependency wiring is required
- Modify: tests/test_web_api.py
- Create: tests/test_product_analysis_parity.py

**Step 1: Write a failing legacy parity test**

Run the same public sample through:

- execute_analysis_pipeline via Product AnalysisService;
- run_uploaded_case.

Compare:

- Overall_status;
- overall_score;
- hard_constraint_passed;
- stage_count;
- VOH_min;
- Max_ripple;
- data_source;
- engineering_validity;
- must_resimulate.

**Step 2: Verify the test fails for the expected duplication boundary**

The initial failure should show the new service is not yet used by the legacy runner, not a metric mismatch caused by the fixture.

**Step 3: Refactor run_uploaded_case**

Keep CaseRunResult and paths unchanged. Translate UploadedCaseConfig into the shared pipeline request. Continue writing case_status.json and the existing product_demo layout.

Do not create a formal ProjectRecord for /api/demo/sample-case.

**Step 4: Run legacy regression**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_analysis_parity.py tests/test_web_api.py tests/test_dashboard_api.py tests/test_product_demo_workflow.py tests/test_demo_mainline.py -q
~~~

Expected: PASS with unchanged response and bundle behavior.

**Step 5: Commit**

~~~powershell
python -m ruff check src/goa_eval/web/runners.py tests/test_product_analysis_parity.py tests/test_web_api.py
git diff --check
git add src/goa_eval/web/runners.py src/goa_eval/web/app.py tests/test_web_api.py tests/test_product_analysis_parity.py
git commit -m "refactor: route legacy uploads through shared analysis"
~~~

Only stage app.py if it changed.

---

## Task 6: Add structured issues and evidence indexing

**Files:**

- Create: src/goa_eval/product/issue_service.py
- Create: src/goa_eval/product/evidence_service.py
- Modify: src/goa_eval/product/analysis_service.py
- Modify: src/goa_eval/product/models.py
- Test: tests/test_product_issue_service.py
- Test: tests/test_product_evidence_service.py

**Step 1: Write failing IssueService tests**

Given FAIL_RIPPLE, require an IssueRecord with:

- stable issue_id;
- constraint_key;
- waveform_quality category;
- high severity;
- max_ripple metric reference;
- possible causes;
- recommended actions;
- classification=known.

Unknown failure keys must create classification=unclassified.

**Step 2: Write failing issues.json test**

Run public sample analysis and verify issues.json is part of the published run bundle and references existing evidence/artifacts.

**Step 3: Write failing EvidenceService tests**

Verify:

- normalize_evidence_boundary is used;
- all published ArtifactRefs become EvidenceRecords;
- missing required files produces evidence_incomplete;
- mock_used=true cannot coexist with reportable_as_real_local-simulator=true;
- read-only suggestions cannot be confirmed;
- evidence summary reports complete, incomplete and invalid separately.

**Step 4: Implement IssueRecord and services**

IssueRecord remains an artifact record in Phase 1; do not add an issues table.

Public interfaces:

~~~python
IssueService.build_issues(score, summary, metrics, diagnosis_ref)
EvidenceService.index_analysis_artifacts(run_id, artifact_refs, raw_evidence)
EvidenceService.validate_boundary(evidence)
EvidenceService.summarize_completeness(run_id)
EvidenceService.can_confirm_improvement(candidate, result_run)
~~~

**Step 5: Integrate with AnalysisService**

Generate issues.json before publishing the run directory. Index evidence after publishing. If required evidence is missing, update AnalysisRun to evidence_incomplete.

**Step 6: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_issue_service.py tests/test_product_evidence_service.py tests/test_product_analysis_service.py tests/test_evidence_level.py -q
python -m ruff check src/goa_eval/product tests/test_product_issue_service.py tests/test_product_evidence_service.py
git diff --check
git add src/goa_eval/product/issue_service.py src/goa_eval/product/evidence_service.py src/goa_eval/product/analysis_service.py src/goa_eval/product/models.py tests/test_product_issue_service.py tests/test_product_evidence_service.py
git commit -m "feat: index analysis issues and evidence"
~~~

**Batch B checkpoint**

Run all product backend tests plus old upload and Dashboard tests. Report and stop for review.

---

## Task 7: Add the versioned Product API

**Files:**

- Create: src/goa_eval/product_api/__init__.py
- Create: src/goa_eval/product_api/app.py
- Create: src/goa_eval/product_api/schemas.py
- Create: src/goa_eval/product_api/dependencies.py
- Create: src/goa_eval/product_api/errors.py
- Create: src/goa_eval/product_api/routes/__init__.py
- Create: src/goa_eval/product_api/routes/workspaces.py
- Create: src/goa_eval/product_api/routes/projects.py
- Create: src/goa_eval/product_api/routes/inputs.py
- Create: src/goa_eval/product_api/routes/analyses.py
- Create: scripts/run_product_api.py
- Test: tests/test_product_api.py

**Step 1: Write failing container tests**

Build ProductContainer with temporary SQLite and LocalArtifactStore. Verify production settings are not used in tests.

**Step 2: Write failing workspace and project API tests**

Verify:

- POST /api/v1/workspaces returns 201;
- POST /api/v1/projects validates Profile;
- GET project overview returns stable counts;
- design-version list is project-scoped;
- every success response includes schema_version=1.0.

**Step 3: Write failing input API tests**

Multipart preview must:

- accept waveform plus optional params/netlist/image;
- return preview and Input Snapshot;
- return 422 INPUT_PREVIEW_FAILED for malformed input;
- reject unsafe filenames;
- not expose server absolute paths.

**Step 4: Write failing analysis API tests**

Verify:

- POST analysis-runs executes the run;
- GET status, bundle, issues and evidence;
- evidence DTO contains exact boundaries;
- unknown resources use stable errors;
- illegal state returns 409 ANALYSIS_STATE_CONFLICT;
- internal failure returns ANALYSIS_EXECUTION_FAILED without traceback leakage.

**Step 5: Implement Pydantic DTOs**

Keep API DTOs separate from domain and ORM records.

Success:

~~~json
{"schema_version":"1.0","data":{}}
~~~

Error:

~~~json
{
  "error_code":"PROJECT_NOT_FOUND",
  "message":"Project was not found.",
  "details":{},
  "retryable":false,
  "artifact_refs":[]
}
~~~

**Step 6: Implement error mapping and routes**

Domain services never raise HTTPException. Product API maps errors centrally.

**Step 7: Add local runner**

scripts/run_product_api.py starts src.goa_eval.product_api.app:app with documented local defaults. Do not change the canonical Vercel entrypoint in Phase 1.

**Step 8: Run tests and commit**

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_api.py tests/test_product_analysis_parity.py tests/test_web_api.py -q
python -m ruff check src/goa_eval/product_api scripts/run_product_api.py tests/test_product_api.py
git diff --check
git add src/goa_eval/product_api scripts/run_product_api.py tests/test_product_api.py
git commit -m "feat: add versioned CircuitPilot product API"
~~~

---

## Task 8: Build the polished React engineering workspace

**Required skills before implementation:**

- Invoke @frontend-skill and follow its visual-design workflow.
- Invoke @test-driven-development.
- Use @playwright or the available browser-verification skill after tests and build.

**Files:**

- Modify: frontend/package.json
- Modify: frontend/package-lock.json
- Modify: frontend/src/App.tsx
- Modify: frontend/src/styles.css
- Create: frontend/src/router.tsx
- Create: frontend/src/api/productClient.ts
- Create: frontend/src/types/product.ts
- Create: frontend/src/layouts/ProductShell.tsx
- Create: frontend/src/components/product/AppSidebar.tsx
- Create: frontend/src/components/product/ProjectContextBar.tsx
- Create: frontend/src/components/product/PageHeader.tsx
- Create: frontend/src/components/product/SectionPanel.tsx
- Create: frontend/src/components/product/EmptyState.tsx
- Create: frontend/src/components/product/ErrorState.tsx
- Create: frontend/src/components/product/LoadingSkeleton.tsx
- Create: frontend/src/components/product/ArtifactList.tsx
- Create: frontend/src/components/analysis/IssueList.tsx
- Create: frontend/src/pages/ProjectListPage.tsx
- Create: frontend/src/pages/NewProjectPage.tsx
- Create: frontend/src/pages/ProjectOverviewPage.tsx
- Create: frontend/src/pages/DesignVersionPage.tsx
- Create: frontend/src/pages/AnalysisRunPage.tsx
- Create: frontend/src/pages/DemoPage.tsx
- Test: frontend/src/router.test.tsx
- Test: frontend/src/api/productClient.test.ts
- Test: frontend/src/pages/ProjectListPage.test.tsx
- Test: frontend/src/pages/NewProjectPage.test.tsx
- Test: frontend/src/pages/DesignVersionPage.test.tsx
- Test: frontend/src/pages/AnalysisRunPage.test.tsx
- Modify test: frontend/src/App.test.tsx

**Step 1: Install React Router**

~~~powershell
Set-Location frontend
npm install react-router-dom@^7
Set-Location ..
~~~

Review package.json and lockfile. Do not add a large component framework.

**Step 2: Write failing router tests**

Using createMemoryRouter, verify:

- /workspaces/default/projects;
- /projects/new;
- /projects/:id/overview;
- /projects/:id/versions/:versionId;
- /analysis/:runId;
- /demo;
- unknown route produces a designed not-found state.

Old case_id Demo data remains available through DemoPage.

**Step 3: Write failing product-client tests**

Mock fetch only at the network boundary. Preserve error_code, details, retryable and artifact_refs.

**Step 4: Write failing page-state tests**

Cover:

- project-list empty, loading, error and populated states;
- new-project validation and Profile boundary;
- DesignVersion upload, preview warning, preview failure and analysis submission;
- AnalysisRun running, completed, hard-constraint failed, evidence incomplete and partial-resource failure;
- must_resimulate visible beside read-only suggestions.

**Step 5: Define visual tokens in styles.css**

Implement the approved Evidence Cockpit system:

- navy background;
- cyan information/action;
- amber evidence warning;
- emerald verified;
- red failure;
- slate neutral;
- 8px spacing rhythm;
- 12px panel radius;
- 232px desktop sidebar;
- max 1600px content;
- clear focus rings;
- reduced-motion override;
- reusable skeleton animation.

Avoid a giant Demo-style title on product pages.

**Step 6: Build ProductShell and base components**

Use semantic nav, header, main and section elements. All status components use icon plus text, never color alone.

**Step 7: Build pages**

Reuse current OverviewCards, EvidenceBoundaryCard, ConstraintStatusPanel, FiguresGallery and ReportsPanel through props/adapters. Do not copy their markup.

The AnalysisRun page visual order is:

1. breadcrumb and context;
2. page header and run status;
3. evidence boundary;
4. constraints and Issues;
5. metrics and figures;
6. read-only suggestions;
7. reports and Artifacts.

**Step 8: Run frontend tests and build**

~~~powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
~~~

Expected: all Vitest tests pass and TypeScript/Vite production build exits 0.

**Step 9: Run browser visual verification**

Start the Product API and frontend. Use the public GOA sample.

Capture temporary screenshots, not committed files, at:

- 1440x900;
- 1024x768;
- 390x844.

Verify:

- no page-level horizontal overflow;
- navigation and primary action are visible;
- evidence boundary is visible without searching;
- Project, Preview, Analysis and Hard Constraint states are visually distinct;
- long IDs wrap or truncate with accessible title;
- tables scroll inside their container;
- mobile layout remains usable;
- focus states are visible;
- reduced motion disables entrance movement;
- no low-contrast text;
- no clipped chart or report panel;
- product pages look like a cohesive engineering tool, not a collection of Demo cards.

If a visual defect is found, write a failing component or layout regression test where practical before fixing.

**Step 10: Commit**

~~~powershell
git diff --check
git add frontend/package.json frontend/package-lock.json frontend/src
git commit -m "feat: add polished GOA analysis workspace"
~~~

---

## Phase 1 final verification

Use @verification-before-completion.

### Backend focused verification

~~~powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_product_*.py tests/test_web_api.py tests/test_dashboard_api.py tests/test_product_demo_workflow.py tests/test_circuit_profiles.py -q
python -m ruff check src/goa_eval/product src/goa_eval/product_api tests/test_product_*.py
~~~

### Full Python regression

~~~powershell
$env:PYTHONPATH='src'
python -m pytest -q
~~~

### Frontend verification

~~~powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
~~~

### Product-story verification

Run the public sample through:

1. CLI;
2. legacy upload API;
3. Product API.

Compare overall status, score, hard constraints, stage count, core metrics and exact evidence boundary.

### Visual verification

Repeat the three viewport checks and inspect screenshots. Do not claim visual quality from unit tests alone.

### Scope verification

~~~powershell
git status --short
git diff --check
git diff --name-only <phase1-base>..HEAD
~~~

Confirm the branch contains only Phase 1 source, tests, dependency lock updates and documentation. Exclude databases, uploads, screenshots and unrelated files.

## Phase 1 completion checklist

- GOA Project creation works.
- Baseline DesignVersion creation works.
- Input Preview and Input Snapshot work.
- Preview and Analysis states are distinct.
- GOA analysis completes from the browser.
- Constraints, Issues, figures, reports and evidence render.
- Inputs and outputs are published through Artifact Store.
- SQLite contains metadata only.
- Legacy APIs remain compatible.
- CLI, legacy API and Product API core results match.
- Read-only suggestions remain must_resimulate=true.
- Evidence boundary is exact and visible.
- Python full suite passes.
- Frontend tests and build pass.
- Desktop, tablet and mobile visual checks pass.
- Product UI meets the approved Evidence Cockpit design.
