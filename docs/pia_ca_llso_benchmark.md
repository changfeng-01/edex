# PIA-CA-LLSO Benchmark

## Primary Metrics

- best_feasible_score_under_budget
- convergence_auc
- first_feasible_eval
- fe_at_target
- hard_constraint_pass_rate

## Secondary Metrics

- not_evaluable_rate
- simulation_failure_rate
- mean_violation
- candidate_hit_rate
- l1_discovery_count
- enrichment_factor

## Diagnostic Metrics

- acquisition components
- candidate role coverage
- missing physics feature inputs
- unavailable latent or attention diagnostics

## Ablation Setup

The first benchmark compares:

- random
- ca_llso_raw_distance
- pia_physics_distance

## Evidence Boundary

predicted_score cannot be final evidence because it is produced by the selector model. attention score cannot be final evidence because it explains retrieval behavior. Final claims must come from externally evaluated simulation records.

- data_source = real_simulation_csv
- engineering_validity = simulation_only
