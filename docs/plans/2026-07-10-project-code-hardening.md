# CircuitPilot Project Code Hardening Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` task-by-task with `test-driven-development`, `codegraph`, and `using-git-worktrees`.

**Goal:** Harden CircuitPilot correctness, evidence reporting, Web writes, engineering gates, and maintainability while preserving public surfaces.

**Architecture:** Add strict shared validation at data boundaries, expose coverage and security controls additively, then extract internal responsibilities behind existing facade modules. Every behavior change starts with a failing regression test and each layer is committed independently.

**Tech Stack:** Python 3.10, pandas, FastAPI, pytest, React 19, TypeScript, Vite, Vitest, GitHub Actions.

---

## Execution Batches

1. Record clean-worktree baselines and commit the approved design and plan.
2. Normalize simulation result types and correct case-pack budget and win-rate statistics.
3. Add waveform coverage metadata, strict coverage behavior, and argv-based simulator execution.
4. Add bearer-key write protection, create-only case storage, streaming upload limits, and session-only frontend authorization.
5. Add Ruff/pytest/frontend CI, Python constraints, dependency security updates, and Vite chunking.
6. Extract selector, multi-round, and GOA-hybrid internal responsibilities while retaining facade imports.
7. Update migration documentation, run all verification commands, inspect remote-base scope, and push the feature branch.

## Required Verification

Run focused tests after each red-green cycle. Before each commit run the affected test modules and `python -m ruff check` for touched Python files. Before delivery run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
python -m ruff check src tests
Set-Location frontend; npm test -- --run
npm run build
Set-Location ..; git diff --check
```

The final result must retain all current CLI registrations, public imports, report files, and exact evidence-boundary strings.
