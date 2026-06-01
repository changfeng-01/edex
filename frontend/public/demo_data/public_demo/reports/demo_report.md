# Product Demo Report: public_demo

## Evidence Boundary

- data_source: real_simulation_csv
- engineering_validity = simulation_only
- evidence_level: level_1_external_csv
- simulation_backend: external_csv
- mock_used: False
- pdk_available: False
- ngspice_available: False
- reportable_as_real_ngspice: False
- optimizer_claim_level: candidate_generated

## What To Read

- Run summary: `run_summary_table.csv`
- Constraints: `constraint_table.csv` (fail: 2, pass: 6)
- Candidate ranking: `top_candidates_table.csv`
- Before/after validation: `before_after_table.csv`

## Figures

- `fig01_waveform_overview.png`
- `fig02_constraint_status.png`
- `fig03_metric_comparison.png`
- `fig04_candidate_ranking.png`
- `fig05_before_after_comparison.png`
- `fig06_evidence_card.png`

## Validation State

`validation_status = awaiting_rerun_results`. If this is `awaiting_rerun_results`, no after-run improvement is claimed.
