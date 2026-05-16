# GitHub Upload Checklist

## 1. Upload Precheck

Run these checks before the first public commit:

```bash
python -m pytest -q
rg -n "<replace-with-private-path-pattern>" README.md docs examples configs src tests pyproject.toml .gitignore LICENSE
```

Review any hits manually. Historical notes may mention local paths; public README, docs, examples, and source code should not require them.

## 2. Do Not Upload

Do not upload private or bulky artifacts unless explicitly approved:

- root-level `yuanshi_csv` / `neibucsv`
- `data/waveforms/*`
- full raw simulation CSV files
- `.tr0`, simulator logs, generated waveform dumps
- `outputs/`, `output/`, `report_ppt*/`
- `汇报用/` and `汇报用.zip`
- `.docx`, `.pdf`, temporary office files
- personal absolute paths

## 3. Suggested Public Files

Keep only small public examples:

- `examples/sample_waveform.csv`
- `examples/sample_params.yaml`
- `configs/default_eval.yaml`
- `configs/cascade_720.yaml`
- `docs/*.md`
- tests that generate their own temporary waveform fixtures

## 4. First Git Commands

Only run these after reviewing ignored files:

```bash
git init
git status --short
git add .gitignore LICENSE README.md pyproject.toml src tests configs examples docs
git status --short
git commit -m "chore: prepare CircuitPilot open-source baseline"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

Do not push until the file list is reviewed.

## 5. Branch Workflow

Recommended flow after the first upload:

```bash
git checkout -b feature/<short-name>
python -m pytest -q
git add <changed-files>
git commit -m "feat: <short summary>"
git push -u origin feature/<short-name>
```

Use pull requests for larger metric, schema, or recommendation changes.

## 6. Protecting Simulation Data

- Keep private waveform data outside the repository or under ignored folders.
- Share only small synthetic examples in `examples/`.
- Never paste absolute local paths into README or docs.
- Keep `engineering_validity = simulation_only` in public reports unless a future workflow truly includes physical validation.
