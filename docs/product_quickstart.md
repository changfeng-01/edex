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

The output contains `product_demo_manifest.json`, `evidence_package.json`, `product_report.md`, the accepted deterministic result CSV, and the immutable artifact store. The workflow creates a workspace and project, analyzes a baseline, proposes and approves a candidate, exports a manual simulation job, imports a provenance-locked repeat measurement, evaluates the result version, and compares the two versions. Because the repeat is neutral, the demo intentionally proves that confirmation remains blocked rather than fabricating an improvement.

## Product API

Start the versioned API with the normal ASGI entrypoint:

```powershell
uvicorn goa_eval.product_api.app:app --host 127.0.0.1 --port 8000
```

Profile discovery is read-only:

- `GET /api/v1/profiles`
- `GET /api/v1/profiles/{profile_id}`
- `GET /api/v1/profiles:validate`

Reference profiles are `ota_general_v2`, `comparator_general`, and `oscillator_general`. `ota_general` and its historical aliases remain on the Phase 3 metric contract. The public CSV fixtures under `examples/product_profiles/` are synthetic contract fixtures (`test_only`), not real simulator evidence.

## Vercel frontend

The repository-level Vercel configuration builds the Vite frontend and rewrites browser-history routes to `index.html`. It does not deploy the Python Product API. Set `VITE_PRODUCT_API_BASE_URL` to the separately deployed Product API origin at frontend build time; otherwise the frontend uses same-origin `/api/v1`, which is suitable only when a reverse proxy provides that backend.

## Evidence boundary

Every proposed candidate and imported evaluation retains:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

These artifacts are simulation-only evidence. A selection score is not an evaluated improvement, fixture execution is not external-simulation evidence, and none of the outputs claim silicon validation.
