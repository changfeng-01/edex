# PIA-CA-LLSO Paper Figures

This directory contains the manuscript figure package generated from the current repository state.

## Regenerate

```bash
python scripts/build_pia_paper_figures.py
```

Optional:

```bash
python scripts/build_pia_paper_figures.py --validation-dir outputs/pia_phase3_validation
python scripts/build_pia_paper_figures.py --dry-run
```

## Contents

- `figures/`: PNG and PDF figure exports.
- `prompts/image2_prompts.json`: GPT image2 prompt records for the four concept schematics.
- `figure_manifest.md`: source paths, evidence role, supported claims, and unsupported claims.
- `figure_captions_zh.md`: Chinese manuscript caption drafts.

## Evidence Boundary

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

No formal Phase 3 validation_summary.csv was found; figures 5-6 are marked as sample/smoke visualizations.

The generated figures are publication-preparation artifacts. They do not add new experimental evidence and do not claim silicon, tapeout, laboratory, or physical measurement validation.
