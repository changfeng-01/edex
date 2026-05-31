# CircuitPilot Product-Demo Dashboard

This frontend is a static product-demo dashboard for CircuitPilot engineering evidence packages. It reads JSON, PNG, and Markdown files from `public/demo_data/<case_id>/` and does not require a backend.

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

## Current Scope

- Static display only.
- No database, login, permissions, multi-user system, or task queue.
- No Python optimizer or product-demo workflow changes.
- The dashboard preserves evidence fields such as `data_source = real_simulation_csv` and `engineering_validity = simulation_only`.
- `simulation_only` means the package is simulation/CSV evidence. It does not represent physical validation, silicon validation, or tapeout validation.
- `awaiting_rerun_results` means rerun validation is still pending.

## FastAPI Integration Later

Keep the component contracts unchanged and replace the fetch adapter in `src/lib/demoData.ts`.

For example, static paths like:

```text
/demo_data/<case_id>/dashboard_summary.json
```

can later become API paths like:

```text
/api/product-demo/<case_id>/dashboard-summary
```

The page should still receive the same summary, table, figure, manifest, and report shapes.
