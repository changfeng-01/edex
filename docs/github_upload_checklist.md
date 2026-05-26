# GitHub Upload Checklist

## 1. Public-Release Precheck

Run these checks before changing the existing GitHub repository from private to public:

```bash
python -m pytest -q
git status --short --ignored
git ls-files
git grep -n -I -E "(DEEPSEEK_API_KEY|api[_-]?key|apikey|secret|password|token|Authorization|Bearer|sk-[A-Za-z0-9_-]{20,})" -- . ':!frontend/package-lock.json'
rg -n "<replace-with-private-path-pattern>" README.md docs examples configs config src tests pyproject.toml .gitignore LICENSE
```

Review all hits manually. Placeholders such as `.env.example` are expected; real credentials, personal absolute paths, private waveform files, PDK folders, and bulky local reports should not be tracked.

Because changing repository visibility exposes Git history too, also run a history scan before switching visibility:

```bash
git log --all --pickaxe-regex -S"DEEPSEEK_API_KEY|api_key|apikey|secret|password|token|Authorization|Bearer|sk-" --format="%h %ad %s" --date=short
```

If a real secret appears in Git history, rotate that secret before making the repository public. History rewriting is optional only after rotation and should be coordinated carefully.

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

## 4. Visibility Change Flow

For an existing private GitHub repository, do not re-run `git init` or replace the remote. Use the GitHub repository settings to change visibility after the checks above pass.

Recommended local flow for cleanup commits:

```bash
git status --short
python -m pytest -q
git add <changed-files>
git status --short
git commit -m "chore: prepare public repository checks"
git push
```

Do not change repository visibility until the tracked file list and ignored local artifacts have been reviewed.

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
