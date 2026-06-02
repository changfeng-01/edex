# Physics-Guided Hybrid Optimizer

The physics-guided optimizer adds a lightweight circuit-physics prior before a candidate enters the next simulation round. It is not a SPICE replacement, not a silicon-validation method, and not a final proof of optimization quality.

All benchmark and report outputs keep the existing evidence boundary:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

## What It Does

`physics_guided_hybrid` keeps the existing multi-round flow and adds a pre-simulation ranking step:

1. replay valid `next_candidates` from the best previous run;
2. rank unseen sweep-grid points with the physics prior engine;
3. use the existing surrogate ranking when enough history exists;
4. fill remaining budget with the existing diversity fallback.

The physics prior only decides which candidates are more plausible to try next. Every selected candidate still has to be rerun through the simulation workflow before it can be interpreted as evidence.

## Physics Proxies

The engine computes conservative proxies when the required parameters are present:

| Proxy | Meaning |
| --- | --- |
| `rc_delay_proxy` | `R_driver * C_load`, or `C_load / W_eff` when explicit driver resistance is unavailable. |
| `drive_to_load_ratio` | Drive strength relative to load, using `W_eff / C_load` or `1 / rc_delay_proxy`. |
| `storage_to_load_cap_ratio` | Storage capacitance margin relative to load capacitance. |
| `timing_spacing_over_rc` | Timing spacing normalized by the RC proxy. |
| `pulse_width_over_rc` | Pulse width normalized by the RC proxy. |
| `voltage_margin` | `VDD - Vth`. |

Hard physics-prior violations are:

- `voltage_margin <= 0`
- `timing_spacing_over_rc < 2`
- `pulse_width_over_rc < 3`

Missing proxy inputs reduce explainability but do not automatically fail a candidate. A candidate fails the physics prior only when a hard proxy is computable and violates its threshold.

## Output Metadata

Physics-ranked candidates carry these fields through the multi-round leaderboard:

```text
candidate_source = physics_prior_engine
model_status = physics_prior_engine_v1
physics_score
physical_hard_passed
physics_proxy_json
physics_violations
physics_rationale
```

`physics_score` is a ranking prior in `[0, 100]`. It must not be reported as a completed simulation score or physical validation result.

## Benchmark Example

```bash
python -m goa_eval.cli strategy-benchmark \
  --sweep config/sky130_candidate_sweep.yaml \
  --validation-config config/sky130_validation.yaml \
  --mock-ngspice \
  --strategies random,adaptive,surrogate,hybrid_goa,physics_guided_hybrid \
  --seeds 1,2,3 \
  --rounds 2 \
  --max-runs-per-round 3 \
  --output-root outputs/strategy_benchmark_physics
```

The benchmark summary includes `physics_pass_rate`, `avg_physics_score`, and `physics_violation_rate` when a strategy emits physics metadata. These metrics are unavailable for strategies that do not use the physics prior.
