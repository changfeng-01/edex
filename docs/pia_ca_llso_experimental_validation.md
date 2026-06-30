# PIA-CA-LLSO Experimental Validation

This document is generated from `pia-validate` outputs and summarizes the Phase 3 validation protocol.

Boundary labels are fixed:

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true

These results are simulation-only evidence, not physical validation.

## Formal Validation Contract

The formal validation profile uses fixed budgets `[10, 20, 50, 100, 200]`, 20 seeds, and the full method registry:

- `random`
- `ca_llso_raw_distance`
- `pia_physics_distance`
- `pia_capm_distance`
- `adaptive_pia_capm`
- `sklearn_surrogate_baseline`
- `literature_ensemble_hybrid`
- `paper_ca_llso`
- `paper_adaptive_constraint_eval`
- `paper_distributed_multi_constraint`
- `classifier_level_hybrid`
- `pia_evolve_full`

Formal outputs include `fairness_audit.csv`, `leakage_audit.csv`, `scenario_manifest.csv`, `method_registry.json`, `source_lock.json`, and `formal_validation_report.md`.

## Fairness Rule

All methods must use the same scenario, initial history, candidate pool, target score, budget, seed set, scoring config, and result-import rule. Candidate ranking must reject result-derived candidate columns before acquisition. `target_hit` and `simulations_to_target` are derived only from each run's `best_so_far_curve.csv`.

## Current Evidence Boundary

The checked-in `sample_goa` scenario is a local fixture/smoke scenario. It verifies the formal validation machinery and audit outputs, but it does not provide full multi-scenario superiority evidence. Strong claims require additional real or fixed case packs.
