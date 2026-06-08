# ECLIPSE Benchmark

`eclipse_benchmark` is an independent model/algorithm evaluation benchmark. It
does not replace `strategy_benchmark.py`, `goa_strategy_benchmark.py`, or
`multi_agent/benchmark.py`.

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

## Primary Metrics

- `best_feasible_score`
- `normalized_convergence_auc`
- `fe_at_target_score`
- `first_feasible_round`
- `hard_constraint_pass_rate`
- `not_evaluable_rate`
- `candidate_hit_rate`

Only real evaluation results, existing real-simulation CSV-derived history, and
`score_real_evaluation()`-style fields can prove algorithm advantage.
`predicted_score`, `physics_score`, and `attention_score` are internal
acquisition or diagnostic evidence only. `physics_score` is not a final
optimization result, and `attention_score` is diagnostic only.

`not_evaluable` is tracked independently from failed, skipped, and passed.
Mock, proxy, or predicted evidence must not be reported as real optimization
improvement or silicon validation.

## Inputs

Offline replay mode expects:

```text
outputs/eclipse_runs/
  algorithm_name/
    seed_1/
      optimization_history.json
      optimization_leaderboard.csv
      candidate_audit.csv        # optional
      attention_audit.csv        # optional
      ledger.json                # optional
```

ECLIPSE-Opt attention, evidence, and role fields are optional diagnostics. When
they are missing, the benchmark records them as unavailable instead of
fabricating values.

## CLI

```bash
python -m goa_eval.cli eclipse-benchmark \
  --runs-root outputs/eclipse_runs \
  --output-root outputs/eclipse_benchmark \
  --score-threshold 80 \
  --baseline random
```

The module entrypoint also works:

```bash
python -m goa_eval.eclipse_benchmark.benchmark \
  --runs-root outputs/eclipse_runs \
  --output-root outputs/eclipse_benchmark \
  --score-threshold 80 \
  --baseline random
```

## Outputs

- `eclipse_benchmark_summary.json`
- `eclipse_algorithm_leaderboard.csv`
- `eclipse_algorithm_runs.csv`
- `eclipse_convergence_curves.csv`
- `eclipse_candidate_selection_audit.csv`
- `eclipse_metric_audit.json`
- `eclipse_benchmark_report.md`

The leaderboard sorting rule is independent from old benchmark surfaces:
`best_feasible_score_mean` descending, `normalized_convergence_auc_mean`
descending, `fe_at_target_score_mean` ascending with null last,
`target_pass_rate_mean` descending, `hard_constraint_pass_rate_mean`
descending, `not_evaluable_rate_mean` ascending,
`simulation_failure_rate_mean` ascending, then
`eclipse_benchmark_score_mean` descending.

## Future Adapter Interface

Future live algorithm benchmarking can connect through an adapter with:

```python
class OptimizerAdapter:
    name: str

    def initialize(self, initial_samples, param_space, budget, seed):
        ...

    def propose(self, history, n_candidates):
        ...

    def observe(self, evaluated_results):
        ...
```

The current module provides offline replay evaluation and placeholder adapter
shape only. It does not implement the full ECLIPSE-Opt deep learning model.
