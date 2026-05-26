# Public Reproducibility Demo

This demo is the smallest public run path for CircuitPilot. It uses only the checked-in sample waveform and writes generated artifacts to an ignored output directory.

## Setup

```powershell
python -m pip install -e ".[test]"
```

## Run

```powershell
python scripts/run_public_demo.py
```

By default this reads:

```text
examples/sample_waveform.csv
```

and writes:

```text
outputs/public_demo/
```

## Expected Outputs

- `real_summary.json`
- `score_summary.json`
- `real_metrics.csv`
- `optimization_dataset.csv`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `recommendations.md`
- `run_manifest_real.json`

The public demo must keep these boundary markers:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

These mean the run is based on simulation CSV data only. It is not physical silicon validation.

## Custom Output Directory

```powershell
python scripts/run_public_demo.py --output-dir outputs/my_demo
```

The `outputs/` directory is ignored by git, so generated artifacts remain local unless explicitly copied into a public example folder.
