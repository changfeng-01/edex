# Product Demo Result Reading Guide

## Tables

- `run_summary_table.csv`: one-row case overview with score, status, evidence boundary, candidate status, and validation status.
- `constraint_table.csv`: hard constraints with pass/fail status, current value, threshold, and reason.
- `top_candidates_table.csv`: Top 10 candidates in a readable format. If no candidate file exists, the table says `awaiting_candidate_generation`.
- `before_after_table.csv`: baseline and rerun comparison. If rerun data is missing, it says `awaiting_rerun_results` and does not claim improvement.

## Figures

- `fig01_waveform_overview.png`: waveform overview if `waveform.csv` exists; otherwise a placeholder.
- `fig02_constraint_status.png`: pass/fail count for hard constraints.
- `fig03_metric_comparison.png`: compact view of key summary metrics.
- `fig04_candidate_ranking.png`: Top 10 candidate ranking.
- `fig05_before_after_comparison.png`: rerun comparison, or an awaiting-rerun placeholder.
- `fig06_evidence_card.png`: data source, engineering validity, backend, and evidence-level summary.

## Evidence Boundary

Generated reports and dashboard files preserve these labels unless source artifacts explicitly provide another boundary:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

These outputs are simulation evidence only. They do not claim physical validation, silicon validation, tape-out proof, or lab verification.
