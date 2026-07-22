# Product Demo Quickstart

Run the complete local prototype demo mainline with one command:

```bash
python -m goa_eval.cli demo
```

If the package is installed as a console script, the equivalent command is:

```bash
circuitpilot demo
```

This evaluates `examples/sample_waveform.csv`, generates recommendations, creates deterministic next candidates from `examples/sample_params.yaml` with seed `42`, writes a mock LLM parameter analysis without an API key, packages the result under `outputs/product_demo/public_demo/`, and syncs dashboard files to `frontend/public/demo_data/public_demo/`.

The generated `demo_mainline_manifest.json` records the command, input files, output directories, and the evidence boundary. The boundary remains `data_source = real_simulation_csv` and `engineering_validity = simulation_only`; the demo does not claim physical validation.

Build a handoff-ready CircuitPilot demo package from existing run artifacts:

```bash
python scripts/run_product_demo.py \
  --input-dir examples/demo_run \
  --output-dir outputs/product_demo \
  --case-id public_demo
```

The same workflow is available through the main CLI:

```bash
python -m goa_eval.cli product-demo \
  --input-dir examples/demo_run \
  --output-dir outputs/product_demo \
  --case-id public_demo
```

The output package is written to `outputs/product_demo/public_demo/`.

## Output Layout

- `01_input_snapshot/`: input artifact manifest and availability.
- `02_evaluation/`: run summary and hard-constraint tables.
- `03_candidates/`: top candidate table.
- `04_validation/`: before/after validation table.
- `05_figures/`: six presentation figures.
- `06_dashboard_data/`: dashboard JSON and presentation manifest.
- `07_report/`: executive summary, demo report, and handoff notes.

This workflow organizes existing artifacts. It does not execute a local simulator or perform physical validation.
