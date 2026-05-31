# Product Demo Quickstart

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

This workflow organizes existing artifacts. It does not rerun ngspice, fetch a PDK, or perform physical validation.
