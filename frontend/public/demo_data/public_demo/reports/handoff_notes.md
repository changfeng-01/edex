# Handoff Notes: public_demo

## How This Package Was Built

Run from the repository root:

```bash
python -m goa_eval.cli product-demo --input-dir D:/EDA大赛/outputs/real_720_files --output-dir outputs/product_demo --case-id public_demo
```

## Missing Optional Inputs

- validation_summary.csv, waveform.csv

## Evidence Rules For Teammates

- Keep `engineering_validity = simulation_only` unless a source artifact explicitly provides another boundary.
- Add rerun or validation artifacts before claiming improvement.
- Do not add claims of physical validation, silicon validation, tape-out proof, or lab verification to this package.
