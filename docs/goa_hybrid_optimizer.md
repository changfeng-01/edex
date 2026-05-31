# Hybrid GOA Optimizer

## 1. Task Boundary

`hybrid-goa-optimize` is a GOA-first, simulation-only optimizer. It reads existing GOA evaluation artifacts such as `optimization_history.json`, `optimization_leaderboard.csv`, or compatible benchmark CSV files, then proposes the next candidate parameter sets.

It does not require real ngspice, does not depend on SKY130, and does not claim physical, silicon, or lab validation. Outputs are candidate recommendations for the next simulation round.

Boundary labels are preserved in generated artifacts:

- `engineering_validity = simulation_only`
- `data_source = benchmark-derived`
- `evidence_level = csv-derived`
- `simulation_backend = no_real_ngspice_required`
- `mock_used = false`

## 2. Algorithm Structure

The optimizer combines three candidate sources:

- `surrogate`: samples the parameter space, predicts GOA quality metrics, and ranks candidates with a lightweight model when enough data is available.
- `repair`: diagnoses failure modes and applies targeted parameter mutations.
- `exploration`: keeps diverse parameter-space coverage so the search does not collapse onto one local pattern.

The default candidate mix is:

```yaml
hybrid_candidate_mix:
  surrogate: 0.5
  repair: 0.3
  exploration: 0.2
```

If training data is too small, the surrogate path reports `model_status = fallback_insufficient_data` and falls back to rule-based predictions rather than pretending a useful model was learned.

## 3. Failure-Guided Repair

Repair logic uses GOA metric symptoms to choose parameter categories:

- High `Max_overlap_ratio`: timing, drive, and load parameters; rationale `reduce overlap / improve stage separation`.
- High `Max_ripple`: load, capacitance, and drive parameters; rationale `reduce ripple / improve waveform stability`.
- High `Max_voltage_loss`: drive, load, and resistance parameters; rationale `reduce voltage loss / improve drive margin`.
- High `Delay_std`: timing and drive parameters; rationale `reduce delay dispersion`.
- `rank_status = not_evaluable` or high `not_evaluable_metric_count`: conservative changes; rationale `recover evaluability before aggressive optimization`.

Parameter names are categorized heuristically, so the flow works with project-specific names such as `clk_delay`, `drive_width`, `load_cap`, `R_driver`, or other nearby naming styles.

## 4. Pareto Evaluation

`goa_eval.pareto` provides:

- `pareto_rank(frame, objectives)`
- `is_dominated(a, b, objectives)`
- `select_knee_points(frame)`
- `classify_candidate_style(frame)`

Default objectives minimize `Max_overlap_ratio`, `Max_ripple`, `Max_voltage_loss`, `Delay_std`, and `not_evaluable_metric_count`, while maximizing `overall_score`, `hard_constraint_passed`, `target_passed`, and `LowFreqStable`.

Hard constraints gate interpretation before soft score. A hard-constraint-passing candidate is preferred over a failing candidate even when the failing candidate has a higher soft score.

## 5. CLI Usage

```bash
python -m goa_eval.cli hybrid-goa-optimize \
  --history outputs/run/optimization_history.json \
  --leaderboard outputs/run/optimization_leaderboard.csv \
  --param-space examples/sample_params.yaml \
  --output-root outputs/hybrid_goa \
  --max-candidates 30 \
  --seed 42
```

`--history` is optional when a leaderboard is available. `--param-space` should use the existing CircuitPilot parameter-space YAML shape.

## 6. Output Files

The command writes:

- `hybrid_candidates.csv`: all ranked candidates with source, parameters, predicted metrics, Pareto rank, style, rationale, and evidence fields.
- `hybrid_candidates.md`: readable top-candidate notes.
- `pareto_front.csv`: only Pareto-front candidates.
- `pareto_summary.json`: objective config, front count, style winners, predicted pass rates, and benchmark proxy metrics.
- `hybrid_optimizer_summary.json`: machine-readable run boundary, inputs, model status, source counts, and Pareto summary.
- `hybrid_optimizer_report.md`: report for review or advisor discussion.

Key candidate fields include:

- `candidate_source`
- `parameters_json`
- `changed_parameters`
- `predicted_overall_score`
- `predicted_Max_overlap_ratio`
- `predicted_Max_ripple`
- `predicted_Max_voltage_loss`
- `predicted_Delay_std`
- `predicted_hard_constraint_passed`
- `pareto_rank`
- `candidate_style`
- `repair_operator`
- `recommendation_rationale`

## 7. Baseline Difference

Compared with `random`, this optimizer uses historical GOA evidence and parameter-space structure. Compared with `adaptive`, it explicitly separates model-predicted candidates, failure-guided repair candidates, and exploration candidates, then performs multi-objective Pareto ranking instead of sorting only by `overall_score`.

The strategy benchmark framework now recognizes `repair` and `hybrid_goa` strategy names and summarizes proxy metrics such as:

- `pareto_front_hit_rate`
- `avg_pareto_rank`
- `best_predicted_score_mean`
- `repair_candidate_ratio`
- `surrogate_candidate_ratio`
- `exploration_candidate_ratio`
- `candidate_diversity_score`

These are prediction / candidate-quality proxy fields unless backed by a later simulation run. They must not be reported as `real_improvement`, `validated_gain`, or `silicon_verified`.
