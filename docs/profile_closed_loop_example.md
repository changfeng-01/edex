# Profile Closed-Loop Validation Example

This example validates the profile-aware candidate path end to end:

1. start from a public waveform CSV;
2. add OP/AC/DC/TRAN companion metric CSVs;
3. run `evaluate-real --topology two_stage_opamp`;
4. generate recommendations from `score_summary.json`;
5. generate `next_candidates.csv` from profile `candidate_rules`;
6. write `closed_loop_validation.json` as a compact proof of the run.

Run:

```bash
python scripts/run_profile_closed_loop_example.py
```

Default output:

```text
outputs/profile_closed_loop_example/
```

Important files:

- `analysis_metrics.json`
- `score_summary.json`
- `recommendations.md`
- `next_candidates.csv`
- `closed_loop_validation.json`

Expected behavior:

- `score_summary.json` resolves `topology_profile = ota`.
- `analysis_metric_penalties` includes profile metrics such as `dc_gain_db` and `static_power_w`.
- `next_candidates.csv` includes matching next-run parameter candidates from `examples/profile_closed_loop_params.yaml`, such as `m1_width`, `m2_width`, `load_cap`, or `ibias`.

This is still a simulation-only validation example. It proves that profile metrics can drive next-run candidate generation; it is not physical validation and does not mean a completed automatic optimization loop.

## Optional SKY130/ngspice Check

On a machine with `ngspice` and a SKY130 PDK installed, run a small real simulator pass with:

```bash
python -m goa_eval.cli sky130-sweep \
  --sweep config/sky130_sweep.yaml \
  --pdk-root /path/to/sky130/pdk \
  --split train \
  --max-rows 1 \
  --max-runs 2 \
  --output-root outputs/sky130_real_closed_loop
```

Then inspect:

- `outputs/sky130_real_closed_loop/sky130_sweep_runs.csv`
- `outputs/sky130_real_closed_loop/sky130_sweep_leaderboard.csv`
- each run directory's `analysis_metrics.json`
- each run directory's `next_candidates.csv`
- `outputs/sky130_real_closed_loop/next_param_space.yaml`

The same boundary applies: these files are `real_simulation_csv` / `simulation_only` artifacts, not silicon or physical test evidence.
