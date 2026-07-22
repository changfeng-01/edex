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

## Optional External-Simulation Check

Export a run from the simulator of choice and place `waveform.csv` plus optional
OP/AC/DC/TRAN companion CSV files in one input directory. Import it with:

```bash
python -m goa_eval.cli simulate-run \
  --adapter csv-import \
  --input-dir /path/to/exported/run \
  --output-dir outputs/external_closed_loop
```

Then inspect `analysis_metrics.json`, `score_summary.json`, and
`next_candidates.csv`. These remain `real_simulation_csv` / `simulation_only`
artifacts, not silicon or physical-test evidence.
