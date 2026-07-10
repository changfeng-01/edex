# CircuitPilot Project Code Hardening Design

## Goal

Improve correctness, evidence integrity, public-write safety, reproducibility, and maintainability without changing existing CLI command names, public import paths, report filenames, or evidence-boundary labels.

## Architecture

Work proceeds in five independently verified layers: strict result and statistics validation, waveform coverage and simulator execution, Web write-path security, engineering gates and frontend performance, then compatibility-preserving hotspot extraction. Strict validation fails closed; exploratory workflows retain compatibility only where the result is explicitly marked partial or non-formal.

The exact labels `data_source = real_simulation_csv`, `engineering_validity = simulation_only`, and `must_resimulate = true` remain unchanged. Existing facade modules continue exporting their current public symbols while internal responsibilities move into focused helpers.

## Interfaces

- Simulation imports normalize accepted boolean spellings and reject empty IDs, non-finite scores, and ambiguous values.
- Case-pack publication statistics are ordered by budget and compare only methods with actual evidence.
- Waveform outputs add expected/observed stage coverage and a strict coverage switch.
- External simulators prefer an argv contract with `shell=False`; legacy shell strings are non-formal compatibility only.
- Web POST routes optionally require a bearer key, create case directories without replacement, and enforce streaming upload limits.
- Frontend write authorization is session-only and never compiled into the static bundle.

## Compatibility And Delivery

Implementation is isolated on `codex/project-code-hardening`. The dirty parent workspace, including the uncommitted waveform diagnostic training feature, is excluded. Changes are committed by layer, fully verified, pushed as a feature branch, and not merged into the dirty parent branch automatically.
