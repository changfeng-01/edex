# CircuitPilot Dashboard API

This FastAPI service is a read-only adapter over product-demo artifact packages. It lets a frontend dashboard read the generated JSON, CSV, PNG, and Markdown outputs through stable API endpoints instead of fetching copied static files directly.

The service does not run a local simulator, does not run the optimizer, does not change validation summaries, and does not promote pending candidate suggestions into validated improvements.

## Start

```powershell
python scripts/run_dashboard_api.py
```

or:

```powershell
uvicorn goa_eval.web_api.app:app --reload --host 127.0.0.1 --port 8000
```

## Configuration

```powershell
$env:CIRCUITPILOT_PRODUCT_DEMO_ROOT = "outputs/product_demo"
$env:CIRCUITPILOT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
```

`CIRCUITPILOT_PRODUCT_DEMO_ROOT` defaults to `outputs/product_demo`.

`CIRCUITPILOT_ENABLE_BUILD_API` defaults to false. When it is not set to `1`, `true`, `yes`, or `on`, `POST /api/cases/{case_id}/build-demo` returns `403` with `build API disabled`.

## API

- `GET /api/health`
- `GET /api/cases`
- `GET /api/cases/{case_id}/summary`
- `GET /api/cases/{case_id}/tables`
- `GET /api/cases/{case_id}/figures`
- `GET /api/cases/{case_id}/figures/{filename}`
- `GET /api/cases/{case_id}/reports`
- `GET /api/cases/{case_id}/reports/{filename}`
- `GET /api/cases/{case_id}/manifest`
- `GET /api/cases/{case_id}/bundle`
- `POST /api/cases/{case_id}/build-demo` when explicitly enabled

`/api/cases/{case_id}/bundle` returns the first-screen dashboard payload in one call:

```json
{
  "case_id": "public_demo",
  "summary": {},
  "tables": {},
  "figures": [],
  "reports": [],
  "manifest": {}
}
```

If `dashboard_tables.json` is missing, the API falls back to:

- `02_evaluation/run_summary_table.csv`
- `02_evaluation/constraint_table.csv`
- `03_candidates/top_candidates_table.csv`
- `04_validation/before_after_table.csv`

Missing JSON or CSV files return structured empty states instead of crashing the service.

## Frontend Use

For Vite development, set:

```text
VITE_API_BASE_URL=http://localhost:8000
```

Recommended frontend loading behavior:

```text
if VITE_API_BASE_URL exists:
    fetch API
else:
    fetch static demo_data
```

Static mode still reads `frontend/public/demo_data/<case_id>/`. API mode reads `http://localhost:8000/api/cases/<case_id>/bundle` and related endpoints.

## Evidence Boundary

This API only reads product-demo result packages.

`engineering_validity = simulation_only` means the current package is simulation or CSV evidence. It is not physical validation, silicon validation, tapeout validation, or measured lab validation.

`awaiting_rerun_results` means after-run validation is still pending. It must not be interpreted as a validated improvement.

Evidence fields such as `data_source = real_simulation_csv`, `engineering_validity = simulation_only`, `simulation_backend`, and `optimizer_claim_level` are returned as written by the product-demo package.

## Path Safety

`case_id` is limited to letters, numbers, `_`, `-`, and `.`. Figure and report filenames must be plain filenames and are restricted to the expected directories:

- figures: `05_figures/*.png`, `*.jpg`, `*.jpeg`, `*.webp`
- reports: `07_report/*.md`

The API rejects paths that escape the configured product-demo root.
