# CircuitPilot Product-Demo Dashboard

This frontend is a product-demo dashboard for CircuitPilot engineering evidence packages. It can read static JSON, PNG, and Markdown files from `public/demo_data/<case_id>/`, or it can use the FastAPI dashboard adapter.

## Run

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The default case is `public_demo`.

To inspect another copied package:

```text
http://127.0.0.1:5173/?case_id=<case_id>
```

## Copy Product-Demo Data

For a package generated at:

```text
outputs/product_demo/<case_id>/
```

copy files into:

```text
frontend/public/demo_data/<case_id>/
```

Expected copy layout:

```text
outputs/product_demo/<case_id>/06_dashboard_data/*.json
  -> frontend/public/demo_data/<case_id>/

outputs/product_demo/<case_id>/05_figures/*.png
  -> frontend/public/demo_data/<case_id>/figures/

outputs/product_demo/<case_id>/07_report/*.md
  -> frontend/public/demo_data/<case_id>/reports/
```

The checked-in `public_demo` data is a static example copied from `outputs/product_demo/public_demo/`.

## API Mode

Create `frontend/.env` from `frontend/.env.example`:

```text
VITE_API_BASE_URL=http://localhost:8000
```

Static mode reads `public/demo_data/<case_id>/`. API mode should read the FastAPI service, starting with:

```text
GET /api/cases/<case_id>/bundle
```

Keep static JSON fallback available when `VITE_API_BASE_URL` is not set.

## Current Scope

- Static display plus optional API-backed data loading.
- No database, login, permissions, multi-user system, or task queue.
- No Python optimizer or product-demo workflow changes.
- The dashboard preserves evidence fields such as `data_source = real_simulation_csv` and `engineering_validity = simulation_only`.
- `simulation_only` means the package is simulation/CSV evidence. It does not represent physical validation, silicon validation, or tapeout validation.
- `awaiting_rerun_results` means rerun validation is still pending.

See `../docs/dashboard_api.md` for backend startup, endpoint list, and evidence-boundary notes.
