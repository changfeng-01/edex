# PIA-CA-LLSO

跨电路迁移与 CAPM V4 的物理、数学、数据和验证契约见
[`pia_cross_circuit_transfer_v4_zh.md`](pia_cross_circuit_transfer_v4_zh.md)。

PIA-CA-LLSO is an experimental optimizer module inside the existing EDA repository. It emits next-run simulation suggestions for expensive circuit optimization.

## 1. Method Background

The module targets candidate selection under limited simulation budget. It keeps the current project boundary explicit:

- data_source = real_simulation_csv
- engineering_validity = simulation_only

For the formal paper-facing definition of the problem, objectives, formulas, CAPM-Distance, acquisition functions, and end-to-end pseudocode, use `docs/pia_ca_llso_formal_method_zh.md` as the single source of terminology. In particular, `overall_score` is the single-run simulation score, `objective_score` is the profile-weighted scoring objective, `acquisition_score` is the next-run simulation priority, and `simulations_to_target` is the validation outcome.

## 2. CA-LLSO Baseline

The baseline follows classifier-assisted LLSO style candidate selection: classify candidate levels, find predicted L1-like candidates, then rank by raw parameter-space distance to known L1 samples.

## 3. Raw Euclidean Distance Limitation

Raw parameter distance treats all numeric parameters as comparable, even when circuit behavior depends on ratios, loads, margins, and timing proxies.

## 4. Physics Features phi(x)

The first implementation extracts GOA-profile and generic physical features such as W/L, Cboot/Cload, pullup/pulldown ratio, clock slew proxy, and voltage margins.

## 5. Level Classifier

The labeler assigns L1/L2/L3/L4 from externally evaluated rows. Hard failures cannot enter L1/L2. predicted_only rows cannot enter external benchmark scoring.

## 6. Physics Distance

Physics distance computes weighted distance in feature space:

`sqrt(sum_k w_k * (phi_i_k - phi_j_k)^2)`

## 6.1 CAPM-Distance

`pia_capm_distance` adds a no-training research distance for candidate selection:

```text
D_capm(x, y) =
  D_tensor(x, y)
+ lambda_barrier * D_barrier(x, y)
+ lambda_graph * D_geodesic(x, y)
+ lambda_missing * D_missing(x, y)
```

The tensor term compares GOA physics features with anisotropic weights and small coupling terms such as `Ron*Cload` with clock slew. The barrier term raises the pre-simulation risk cost near low voltage margin, weak bootstrap/load margin, high drive-load proxy, or unbalanced pull-up/pull-down ratios. The geodesic term builds a small kNN graph over candidates and history, then measures the shortest path to the L1 basin. The missing term prevents absent physics inputs from being treated as a zero-distance match.

CAPM-Distance is a selection proxy only. It does not train a model, does not use result columns such as `overall_score` or `hard_constraint_passed` as distance features, and does not replace the next simulation run.

## 7. Learned Latent Metric

The first version exposes a PCA-based latent interface and keeps torch optional. If torch is absent, the optional encoder returns unavailable without affecting the basic flow.

## 8. Memory Attention

The first version uses numpy dot-product attention over historical samples, with optional physics-distance penalty. Attention supports candidate explanation, not final proof of algorithm quality.

## 9. Acquisition Function

Candidate acquisition combines P(L1), predicted score, P(hard_pass), uncertainty, attention mass, distance, and diversity.

## 10. Closed-Loop Evolution

The `pia-evolve` command implements a full closed-loop evolutionary optimizer. It runs multiple generations: each generation labels current history, generates LLSO offspring from L1 teachers and L2/L3 learners, calls the existing `pia-suggest` pipeline for selection, builds a simulation batch, and either stops (offline mode), imports results from CSV (import_results mode), or calls an external simulator (external_command mode).

For detailed usage, see `docs/pia_ca_llso_closed_loop.md`.

## 11. Relation To Existing EDA Project

The module lives under `src/goa_eval/pia_ca_llso/` and is reached through the existing `goa_eval.cli` command system. It does not rewrite `optimize-rounds`, `goa-strategy-benchmark`, or the generic simulation-import commands.

## 12. Current Boundaries And Limits

The current implementation is CSV/offline first. It does not claim silicon validation, physical measurement validation, or completed chip optimization. Outputs are next-run simulation suggestions.

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true
