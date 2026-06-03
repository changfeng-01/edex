# Benchmark Principles

CircuitPilot benchmarks are engineering evaluations, not score-only leaderboards. A benchmark must define the application scenario, fixed inputs, target metric, hard constraints, simulation budget, and evidence boundary before comparing strategies or agents.

## Core Rules

1. Scenario before algorithm: every benchmark records task type, target metric, threshold, shared parameter space, seed set, backend, and budget.
2. Hard constraints before soft scores: evaluability, pulse/function correctness, target pass status, validation status, and boundary safety gate interpretation before `overall_score`.
3. Same-condition comparison: strategy comparisons share the same sweep config, scoring profile, seed set, maximum rounds, and maximum runs per round.
4. Baselines are required: `random` is the naive no-replay baseline; `adaptive` is the engineering baseline; model-based and hybrid strategies are compared against them.
5. Results must be explainable: benchmark rows carry candidate source, changed parameters, trigger metric, rationale, and model status where available.
6. Report more than final score: summaries include target pass rate, hard-fail rate, not-evaluable rate, validation pass rate, simulation efficiency, relative improvement versus `random`, and physics-prior metrics when available.
7. Nominal results require validation context: validation matrix rollups and worst-case values stay visible, and skipped/not-evaluable validation is not treated as proof.
8. Simulation-only boundary is mandatory: `data_source=real_simulation_csv` and `engineering_validity=simulation_only` must remain visible in machine and human-readable outputs.

## Output Families

- Strategy benchmark: compares optimization strategies under shared budget and writes row-level results, per-strategy summary, strategy leaderboard, and report. `physics_guided_hybrid` may add `physics_score`, `physical_hard_passed`, `physics_violations`, and `physics_proxy_json` as pre-simulation candidate-ranking metadata.
- GOA literature benchmark: compares available waveform-derived metrics against literature reference values while marking power, area, and Vth drift dimensions as not evaluable unless the input artifacts contain evidence.
- Multi-agent benchmark: evaluates evidence-chain behavior with explicit hard constraints for routing, artifact discovery, boundary preservation, forbidden claims, and optimization-loop status.

## Interpretation

`not_evaluable` is separate from failed, skipped, and passed. Candidate generation is a next-run suggestion and must not be reported as completed optimization or physical validation. `physics_score` is only pre-simulation ranking evidence and is not a final score. Mock ngspice runs are useful for software checks but are not reportable as real SKY130/ngspice evidence.
