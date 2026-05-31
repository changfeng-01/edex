# Product Demo Handoff Guide

## Add A New Case

1. Produce or collect a run directory with CircuitPilot artifacts such as `real_summary.json`, `score_summary.json`, `real_metrics.csv`, and candidate CSVs.
2. Run:

```bash
python -m goa_eval.cli product-demo \
  --input-dir path/to/run_artifacts \
  --output-dir outputs/product_demo \
  --case-id your_case_id
```

3. Share `outputs/product_demo/your_case_id/` with teammates, advisors, or judges.

## Optional Inputs

The workflow reads these files when present:

- `analysis_metrics.json`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `next_candidates.csv`
- `best_next_candidates.csv`
- `optimization_leaderboard.csv`
- `validation_summary.csv`
- `run_manifest_real.json`
- `figures/figure_manifest.json`
- `waveform.csv`

Missing optional files are recorded in `01_input_snapshot/input_artifact_manifest.json`.

## Evidence Discipline

Keep `engineering_validity = simulation_only` unless a source artifact explicitly and correctly changes the boundary. Add validation or rerun artifacts before claiming improvement. Do not include private simulation files, PDK files, `.tr0` files, generated outputs, or secrets in commits.
