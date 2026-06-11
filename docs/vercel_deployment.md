# CircuitPilot Vercel Deployment

This repo uses two Vercel projects for the upload-analysis demo:

- `circuitpilot-api`: repo root, FastAPI entrypoint at `api/index.py`.
- `circuitpilot-dashboard`: `frontend/`, Vite static dashboard.

## API Project

Create the API project from `origin/main` with the repository root as the project root.

Required environment variables:

```text
BLOB_READ_WRITE_TOKEN=<created by connecting Vercel Blob>
CIRCUITPILOT_CORS_ORIGINS=https://<circuitpilot-dashboard-domain>
```

Optional environment variables:

```text
CIRCUITPILOT_BLOB_PREFIX=web_cases
CIRCUITPILOT_BLOB_API_BASE=https://blob.vercel-storage.com
CIRCUITPILOT_BLOB_API_VERSION=11
```

The API keeps local filesystem writes as temporary invocation workspace only. When
`BLOB_READ_WRITE_TOKEN` is present, uploaded inputs, preview payloads, status
payloads, dashboard bundles, figures, and reports are persisted under:

```text
web_cases/<case_id>/
```

## Dashboard Project

Create the dashboard project from the same GitHub repository with `frontend/` as
the root directory.

Project settings:

```text
Install Command: npm ci
Build Command: npm run build
Output Directory: dist
```

Required environment variable:

```text
VITE_API_BASE_URL=https://<circuitpilot-api-domain>
```

If `VITE_API_BASE_URL` is absent, the dashboard still falls back to the checked-in
static `public_demo` data.

## Smoke Checks

After deployment:

```text
GET  https://<api-domain>/health
POST https://<api-domain>/api/cases/preview
POST https://<api-domain>/api/demo/sample-case
GET  https://<api-domain>/api/cases/<case_id>/bundle
```

The returned evidence boundary must keep these labels unchanged:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```
