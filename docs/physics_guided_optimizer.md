# Physics-Guided Optimizer

`physics_guided_hybrid` is an additive candidate-ranking strategy for the SKY130 multi-round optimization path. It uses `src/goa_eval/physics_engine.py` to rank unsimulated sweep points before the next run, then falls back to the existing surrogate and diversity logic when the physics-prior list does not fill the budget.

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

## Boundary

- `physics_engine.py` is not a SPICE replacement.
- `physics_score` is not a final optimization result.
- The module is only used for simulation-before candidate ranking.
- Every candidate must still be re-simulated before any improvement claim.
- The current flow does not parse GDS, TDO, DRC.rule, or LVS.rule files.
- The benchmark mainline remains based on real simulation outputs, waveforms, netlists, parameter configurations, and evaluation metrics.
- Layout, DRC, and LVS data may be future design context, but they are not part of the current main optimization flow.

## Proxy Meaning

The physics prior follows conservative circuit-design intuition. The 8K LCD GOA thesis material supports these interpretations at a proxy level: GOA speed is tied to load RC and drive capability; larger load capacitance worsens delay; parasitic or overlap capacitance affects power and stability; voltage threshold drift affects robustness. These observations guide candidate ranking only and do not upgrade evidence validity.

- `rc_delay_s`: proxy for RC delay from an effective drive resistance and total capacitance.
- `drive_to_load_ratio`: proxy for transistor drive strength relative to load capacitance.
- `storage_to_load_cap_ratio`: proxy for storage or hold capacitance margin versus load capacitance.
- `timing_spacing_over_rc`: proxy for timing separation relative to the RC delay estimate.
- `pulse_width_over_rc`: proxy for pulse width margin relative to the RC delay estimate.
- `voltage_margin_v`: proxy for supply headroom above threshold voltage.

Hard prior violations are treated as pre-simulation warnings. They do not replace scorer hard constraints and do not prove a candidate failed real circuit behavior.

## Strategy Order

`physics_guided_hybrid` preserves existing orchestration:

1. Replay `next_candidates.csv` from the previous best run when available.
2. Rank remaining unseen grid points with `rank_physics_guided_points()`.
3. Fill any remaining budget with the existing surrogate model ranking.
4. Fill any final gap with the existing diversity fallback.

The `random` strategy remains a no-replay baseline. Existing `adaptive`, `surrogate`, `repair`, and `hybrid_goa` behavior stays separate.

## Benchmark Fields

`strategy-benchmark` carries the physics-prior fields when they are available:

- `physics_score`
- `physical_hard_passed`
- `physics_violations`
- `physics_proxy_json`
- `physics_pass_rate`
- `avg_physics_score`
- `physics_violation_rate`

Leaderboard sorting still prioritizes hard constraints, target status, validation status, final simulation score, and simulation count. It does not sort by `physics_score`.

## Example

```bash
python -m goa_eval.cli strategy-benchmark \
  --strategies random,adaptive,surrogate,hybrid_goa,physics_guided_hybrid \
  --mock-ngspice \
  --seeds 1,2,3 \
  --rounds 2 \
  --max-runs-per-round 3 \
  --output-root outputs/strategy_benchmark
```
