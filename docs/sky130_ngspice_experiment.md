# SKY130 / ngspice Experiment Branch

This branch keeps SKY130 / ngspice work separate from the public lightweight CircuitPilot path.

## Policy

- Do not commit local PDK, volare, or ngspice directories.
- Keep local tool assets under ignored paths such as `tools/`.
- Keep generated simulation outputs under ignored paths such as `outputs/`.
- Keep public result labels explicit:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

These labels mean the result is based on simulation CSV data. It is not physical validation.

## Preflight

Run a local preflight without requiring committed tool assets:

```powershell
python -m goa_eval.cli sky130-experiment `
  --pdk-root tools/volare-pdks/sky130A `
  --ngspice tools/ngspice/Spice64/bin/ngspice.exe `
  --output-dir outputs/sky130_experiment `
  --mock-if-unavailable
```

Outputs:

- `sky130_experiment_preflight.json`
- `sky130_ngspice_experiment.md`

If the local toolchain is present, the preflight reports `ready_for_real_ngspice`. If not, `--mock-if-unavailable` records a skipped status while still verifying the branch wiring.

## Intended Flow

```text
SKY130/ngspice local run -> waveform.csv -> evaluate-real -> evaluate-batch -> optimize-loop
```

Keep SKY130-specific expansion here until the flow is small, reproducible, and safe to describe in public docs without committing local toolchains.
