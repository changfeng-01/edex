# GOA Strategy Benchmark

## 1. Why GOA Benchmark Is Separate from SKY130 Benchmark

`goa-strategy-benchmark` is a GOA-specific candidate-quality proxy benchmark. It is separate from the SKY130-style `strategy-benchmark` for several reasons:

| Aspect | goa-strategy-benchmark | strategy-benchmark (SKY130) |
| --- | --- | --- |
| Target circuit | GOA cascade | SKY130 transistor-level |
| Simulation backend | no real ngspice required | requires ngspice + SKY130 PDK |
| Data source | GOA leaderboard / optimization_history / CSV | SKY130 sweep + ngspice transient |
| Candidate generation | surrogate + repair + exploration + Pareto | sky130_mainline multi-round |
| Benchmark goal | compare candidate-quality proxy | compare real-simulation optimization |

Keeping them separate avoids forcing GOA workflows through SKY130 dependencies. The SKY130 `strategy-benchmark` remains available for ngspice-style validation.

## 2. GOA Benchmark Input

```bash
python -m goa_eval.cli goa-strategy-benchmark \
  --history outputs/.../optimization_history.json \
  --leaderboard outputs/.../optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/goa_strategy_benchmark \
  --strategies random,adaptive,surrogate,repair,hybrid_goa \
  --max-candidates 30 \
  --seeds 1,2,3 \
  --top-k 10
```

At least one of `--history` or `--leaderboard` must be provided. If neither exists, the command reports a clear error.

## 3. Compared Strategies

| Strategy | Type | Description |
| --- | --- | --- |
| **random** | naive baseline | Pure random sampling from parameter space. No replay, no surrogate, no repair. |
| **adaptive** | engineering baseline | Rule-based perturbation around history best parameters. No sklearn model. |
| **surrogate** | model-based | RandomForest surrogate predicts GOA metrics and ranks candidates. Falls back if data is insufficient. |
| **repair** | failure-guided | Diagnoses failure modes (overlap, ripple, voltage loss, delay dispersion) and applies targeted parameter mutations. |
| **hybrid_goa** | proposed method | Combines surrogate (50%), repair (30%), and exploration (20%), then Pareto-ranks the result. |

`physics_guided_hybrid` is treated as an alias for `hybrid_goa`.

## 4. Proxy Metrics

GOA benchmark evaluates candidate quality through proxy metrics, not real simulation results:

### Predicted Score Metrics
- `best_predicted_score`: highest predicted overall_score among candidates
- `topk_predicted_score_mean`: mean predicted score in top-k
- `topk_candidate_quality_proxy_mean`: mean quality proxy in top-k
- `predicted_score_gain_vs_history_best`: improvement over best historical score

### GOA Waveform Proxy Metrics
- `best_predicted_Max_overlap_ratio`
- `best_predicted_Max_ripple`
- `best_predicted_Max_voltage_loss`
- `best_predicted_Delay_std`
- `topk_predicted_*` variants for each

### Pareto Metrics
- `pareto_front_hit_rate`: fraction of candidates on Pareto front
- `avg_pareto_rank`: mean Pareto rank
- `best_pareto_rank`: best (lowest) Pareto rank
- `topk_pareto_rank_mean`: mean Pareto rank in top-k

### Hard Constraint / Evaluability Proxy
- `predicted_hard_constraint_pass_rate`
- `predicted_not_evaluable_rate`
- `repair_first_ratio`
- `conservative_candidate_ratio`

### Diversity Metrics
- `candidate_diversity_score`: ratio of unique parameter combinations
- `changed_parameter_coverage`: fraction of total parameter space touched
- `unique_candidate_ratio`: ratio of unique parameter JSON strings

## 5. How to Interpret the Leaderboard

`goa_strategy_leaderboard.csv` sorts strategies by:

1. `predicted_hard_constraint_pass_rate` (higher is better)
2. `pareto_front_hit_rate` (higher is better)
3. `avg_pareto_rank` (lower is better)
4. `topk_candidate_quality_proxy_mean` (higher is better)
5. `candidate_diversity_score` (higher is better)

This ordering prioritizes safety and Pareto efficiency over raw predicted score.

## 6. Why Proxy Improvement != Validated Gain

**DO NOT** use these terms in GOA benchmark outputs or reports:

- `real_improvement`
- `validated_gain`
- `silicon_verified`
- `real_ngspice_passed`
- `physical_validation`

Instead, use only:

- `predicted_score_gain`
- `candidate_quality_proxy`
- `proxy_improvement`
- `benchmark_proxy_gain`

All output artifacts are labeled:

```yaml
data_source: benchmark-derived
engineering_validity: simulation_only
evidence_level: csv-derived
simulation_backend: no_real_ngspice_required
result_claim: candidate_quality_proxy_only
```

## 7. Relationship with hybrid-goa-optimize

| Command | Purpose |
| --- | --- |
| `hybrid-goa-optimize` | Generate a single set of hybrid candidates from GOA history/leaderboard |
| `goa-strategy-benchmark` | Compare random, adaptive, surrogate, repair, and hybrid_goa candidate-generation strategies |

`goa-strategy-benchmark` calls each strategy independently across multiple seeds, then aggregates the results. The `hybrid_goa` strategy within the benchmark reuses the same candidate-generation logic as `hybrid-goa-optimize`.

## 8. Relationship with strategy-benchmark

| Command | Mainline | Backend |
| --- | --- | --- |
| `goa-strategy-benchmark` | GOA | no real ngspice |
| `strategy-benchmark` | SKY130 | ngspice + PDK |

- `goa-strategy-benchmark`: GOA mainline — compares candidate-generation strategies for GOA circuits.
- `strategy-benchmark`: retained for SKY130 / ngspice-style flows.

Both benchmarks follow a similar output schema (`benchmark_type`, `task_type`, `fairness`, `strategies`, `leaderboard`) so they can be summarized together in the future.

## 9. Output Files

| File | Description |
| --- | --- |
| `goa_strategy_benchmark.csv` | One row per strategy x seed with all metrics |
| `goa_strategy_benchmark_summary.json` | Machine-readable summary with boundary, fairness, and strategy aggregates |
| `goa_strategy_leaderboard.csv` | Strategy comparison sorted by ranking rules |
| `goa_strategy_benchmark_report.md` | Human-readable report with tables and engineering interpretation |
| `candidates/{strategy}_seed_{seed}.csv` | Per-strategy candidate outputs |

## 10. Fairness Guarantees

The `fairness` section in `goa_strategy_benchmark_summary.json` records:

- `same_input_history`: all strategies see the same history (or none)
- `same_input_leaderboard`: all strategies see the same leaderboard (or none)
- `same_param_space`: all strategies use the same parameter space
- `same_candidate_budget`: all strategies produce at most `max_candidates`
- `same_seed_set`: all strategies run with the same seed list
- `same_objective_config`: all strategies use the same Pareto objectives
- `random_baseline_no_replay`: random strategy does not use replay, repair, or surrogate
