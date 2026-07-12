# CircuitPilot Phase 1 Acceptance Record

**Acceptance baseline:** `bc52470dffaac9a238f332569a4722020c797923`

**Date:** 2026-07-12

**Decision:** Accepted for repository-level Phase 1 completion. Production hosting is not accepted because the external Vercel deployment remains failed and its logs require project credentials that are not available in this workspace.

## Accepted product story

The product now supports the complete Phase 1 flow:

```text
Workspace → Project → DesignVersion → Input Preview → InputSnapshot
          → AnalysisRun → Issues / Evidence / Reports / Artifacts
```

The independent `/upload` entry additionally supports:

```text
select or create context → upload waveform + params → preview
→ auto-run when clean / explicit confirmation when warned
→ AnalysisRun page
```

## Scope evidence

| Delivery | Evidence |
|---|---|
| Product domain, repository and artifact storage | Phase 0 Tasks 1-4 and product tests |
| Shared analysis orchestration and legacy parity | Phase 1 Tasks 4-6 and parity tests |
| Versioned Product API | PR #46, commit `41318c11` |
| Evidence Cockpit workspace | PR #46, commit `60fcf46c` |
| Independent upload entry | PR #47, commits `1dd40bf4`, `4569cc1c` |
| Python 3.10 CI closure | PR #48, commits `faae4db1`, `dd46d77b`, `4b6fb1de` |
| Phase 1 merged baseline | `bc52470d` |

## Functional acceptance

- Workspace listing and initialization work through `/api/v1`.
- Existing or new Projects can be selected during upload.
- DesignVersion names, waveform CSV and parameter YAML are required.
- Optional netlist and image attachments remain supported.
- Preview warnings require explicit confirmation; clean previews start analysis automatically.
- Preview retry reuses the locked Project and DesignVersion context.
- Successful analysis redirects to `/analysis/:runId`.
- The existing CLI, `/api/cases`, public Demo and Dashboard remain compatible.
- The Evidence Cockpit exposes Projects, upload, analysis, issues, evidence, figures, reports and artifacts.
- Desktop, tablet and mobile layouts were reviewed at 1440×900, 1024×768 and 390×844 without page-level horizontal overflow.

## Evidence boundary acceptance

The following values are preserved in API responses, UI and artifacts:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Read-only candidate suggestions cannot be promoted to `confirmed_improvement` without matching resimulation evidence.

## Verification record

### Local verification

- Python: `578 passed, 1 skipped, 7 warnings` after the final runtime changes.
- Focused Python 3.10 compatibility regression: `32 passed`.
- Optional/platform dependency regression: `18 passed`.
- Ruff: passed.
- Python 3.10 wheel resolution: 17/17 constraints for Windows and Linux.
- Frontend: 11 test files, 52 tests passed.
- Frontend production build: passed, 2383 modules transformed.
- `git diff --check`: passed.

### GitHub verification

- PR #48 pull-request CI: Python passed, Windows critical passed, frontend passed.
- PR #48 push CI: Python passed, Windows critical passed, frontend passed.
- Merge commit `bc52470d` post-merge CI run `29189437305`: Python passed in 8m44s, Windows critical passed in 2m40s and frontend passed in 33s.

## Known non-blocking warnings

- Starlette/httpx deprecation warning.
- Matplotlib tight-layout/font warnings for generated plots.
- pandas `to_datetime` future warning.
- GitHub Actions warns that Node 20-based action runtimes are deprecated and currently forced to Node 24.

These warnings do not change the accepted Phase 1 product behavior, but should be scheduled as maintenance work.

## External deployment exception

The GitHub Vercel status remains failed. The deployment API rejects unauthenticated log access, and the local Vercel CLI cannot inspect the deployment in this environment. No production deployment was triggered and no speculative Vercel configuration change was made.

Required follow-up before public production release:

1. Grant read access to the Vercel project logs.
2. Confirm the configured Vercel Root Directory and build/output commands.
3. Repair the preview deployment in an isolated deployment PR.
4. Verify `/upload`, SPA fallback and `/api/v1` routing in the hosted environment.

## Phase boundary

Phase 1 is complete at the repository and product-workflow level. Phase 2 must not reinterpret a selection score as engineering improvement. It starts with persisted comparisons and explicit candidate approval, then adds resumable manual simulation export/import and only confirms improvement after evaluated evidence is attached.
