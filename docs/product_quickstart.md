# CircuitPilot Product Quickstart

This quickstart builds the persisted Route C product workflow on the existing `goa_eval` kernel.

## Install and verify

```powershell
python -m pip install -e ".[test,dev]" -c constraints/py310.txt
$env:PYTHONPATH = "src"
python -m pytest tests/test_product_end_to_end.py tests/test_product_reference_profiles.py -q
```

## Build the complete product demo

```powershell
$env:PYTHONPATH = "src"
python scripts/build_product_demo.py `
  --output-dir tmp/product_demo_v1 `
  --database-url sqlite:///tmp/product_demo_v1.db
```

The output contains `product_demo_manifest.json`, `evidence_package.json`, `product_report.md`, the accepted deterministic result CSV, and the immutable artifact store. The workflow creates a workspace and project, analyzes a baseline, proposes and approves a candidate, exports a manual simulation job, imports a deterministic result, evaluates the result version, compares the two versions, and confirms improvement only after evidence checks pass.

## Product API

Start the versioned API with the normal ASGI entrypoint:

```powershell
uvicorn goa_eval.product_api.app:app --host 127.0.0.1 --port 8000
```

Profile discovery is read-only:

- `GET /api/v1/profiles`
- `GET /api/v1/profiles/{profile_id}`
- `GET /api/v1/profiles:validate`

Reference profiles are `ota_general`, `comparator_general`, and `oscillator_general`. Their public CSV fixtures are under `examples/product_profiles/`.

## Evidence boundary

Every proposed candidate and imported evaluation retains:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

These artifacts are simulation-only evidence. A selection score is not an evaluated improvement, mock execution is not real ngspice, and none of the outputs claim silicon validation.
