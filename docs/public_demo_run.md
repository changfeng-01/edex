# Public Demo Run

This repository includes a fixed public demo run under `examples/demo_run/`. It is generated only from the small public inputs in `examples/sample_waveform.csv` and `examples/sample_params.yaml`, so it is safe to commit and reproduce without private waveform data.

## What The Demo Shows

The demo exercises the current CircuitPilot workflow end to end:

- `evaluate-real` reads the public waveform CSV and writes metrics, score, reports, manifest, and figures.
- `recommend` turns the score and metric summary into a human-readable recommendation report.
- `propose-candidates` generates 10 deterministic constrained-random next-run candidates with `seed=42`.
- `analyze-params` writes a DeepSeek-compatible parameter analysis using a fixed mock response, so no API key or network call is required.
- Dashboard data in `frontend/public/data/` is refreshed from the same run.

All demo outputs keep the public boundary labels:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

These labels mean the files are derived from simulation CSV data only. They are not physical test results and do not prove a completed automatic optimization loop.

## Regenerate The Demo

Run from the repository root:

```bash
python scripts/build_public_demo.py
```

The script rewrites `examples/demo_run/` and refreshes `frontend/public/data/`.

To test the script without touching the committed demo directories:

```bash
python scripts/build_public_demo.py \
  --output-dir tmp/public_demo_run \
  --frontend-data-dir tmp/public_dashboard_data
```

## Output Files

The full public bundle lives in `examples/demo_run/`:

- `real_summary.json`
- `score_summary.json`
- `real_metrics.csv`
- `optimization_dataset.csv`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `recommendations.md`
- `next_candidates.csv`
- `next_candidates.md`
- `llm_parameter_analysis.md`
- `llm_parameter_analysis.json`
- `run_manifest_real.json`
- `figures/`

The dashboard currently reads these refreshed files from `frontend/public/data/`:

- `real_summary.json`
- `score_summary.json`
- `real_metrics.csv`
- `optimization_dataset.csv`
- `figures/`

## Known Limitation

The public sample waveform has only three output nodes. The framework still supports configurable larger cascades, including the 720-stage configuration path, but this fixed demo intentionally uses the small public sample so the repository remains lightweight and reproducible.
