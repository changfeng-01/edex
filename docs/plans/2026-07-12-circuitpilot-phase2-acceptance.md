# CircuitPilot Product Phase 2 Acceptance

Date: 2026-07-14  
Branch: `codex/product-phase2-manual-loop`

## Accepted scope

Phase 2 closes the manual optimization and simulation loop without invoking a simulator automatically:

1. create an optimization experiment from a baseline DesignVersion;
2. generate deterministic candidates through existing rule, hybrid, or PIA entrypoints;
3. explicitly approve or reject each candidate with audit records;
4. export approved candidates through the existing simulation-batch contract;
5. preview, validate, quarantine, retry, and commit manually returned CSV results;
6. recover a validating job after service/database restart;
7. create result DesignVersions linked to candidate and simulation-job provenance;
8. compare completed evaluated artifacts, then and only then confirm an improvement.

The exact engineering boundary remains:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Selection scores never authorize `confirmed_improvement`. Imported bytes alone never authorize it either. Confirmation requires an improved comparison between completed baseline and result AnalysisRuns, matching candidate ID, simulation job ID, result DesignVersion, result SHA-256, and evidence boundary.

## Persistence and recovery evidence

- Alembic revision `20260712_02` adds experiments, candidates, simulation jobs, comparisons, and Phase 2 provenance fields.
- Export is idempotent and contains parameter hashes plus the exact evidence boundary.
- Raw imports are quarantined before validation; invalid contracts fail closed and remain retryable.
- Preview manifests and accepted results are immutable content-addressed artifacts.
- The deterministic E2E test disposes the first database engine after preview, creates new repository/service instances, and successfully commits the same import after restart.
- Candidate approval, rejection, export, failed import, retry, and committed import produce audit events.

## Compatibility evidence

The full repository suite covers the legacy CLI, Dashboard API, public Demo, Phase 1 product API/upload flow, waveform evaluation, optimizer modules, and Phase 2 additions. One pre-Phase-2 test originally asserted that the repository had no `add_candidate` method. Phase 2 intentionally adds that repository capability, so the assertion was corrected to verify its actual compatibility intent: read-only analysis suggestions leave the candidate table empty.

No CI workflow change was required because the existing full-suite commands collect the new tests.

## Verification record

- `python -m pytest tests/test_product_analysis_service.py tests/test_product_phase2_e2e.py -q`: **7 passed**
- `python -m pytest -q`: **608 passed, 1 skipped, 7 warnings** in 593.62 seconds
- `python -m ruff check src tests`: **passed**
- `npm test -- --run`: **59 passed** across 14 files
- `npm run build`: **passed**, 2,389 modules transformed
- `git diff --check`: required before the acceptance commit

The warnings are pre-existing dependency/plotting warnings: Starlette's `httpx` migration notice, Matplotlib tight-layout notices, and a pandas datetime future warning. No Phase 2 test warning was introduced.

## Browser acceptance

Playwright CLI acceptance used controlled API responses while the Python E2E test covered real persistence and service behavior.

- **1440 x 900:** experiment page, long candidate ID, explicit approval, candidate-level `must_resimulate`, and transition to the manual-job action.
- **1024 x 768:** simulation-job page, long candidate ID, long result filename, preview warning, retained file selection, reload recovery to `waiting_for_results`, and no premature improvement claim.
- **390 x 844:** vertical workflow, visible keyboard focus, contained table scrolling, evidence-insufficient comparison, zero page-level horizontal scroll, and no `Confirmed improvement` text.
- Browser console: **0 errors, 0 warnings** after the accepted flows.

Playwright screenshots, session state, the temporary CSV, local databases, uploaded results, netlists, waveforms, `node_modules`, and simulator binaries are excluded from the commit.

## Release decision

**Accepted for scoped branch publication.** Phase 2 is a resumable manual simulation loop; it is not an autonomous simulation executor and does not broaden the evidence claim beyond `simulation_only`.
