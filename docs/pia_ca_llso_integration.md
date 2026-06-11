# PIA-CA-LLSO Integration

PIA-CA-LLSO is currently a repository-internal module, not a replacement for the existing optimization pipeline.

## Current Role

PIA reads history CSV and candidate CSV files, labels externally evaluated rows, extracts physics features, ranks candidates, and emits next-run simulation suggestions.

## Existing Pipeline Responsibilities

- Generate netlists
- Run simulators
- Parse waveforms
- Extract metrics
- Save history, leaderboard, and analysis artifacts

## PIA Responsibilities

- Read historical samples
- Assign L1/L2/L3/L4 labels
- Extract physics features
- Compare raw and physics distance strategies
- Select next-run candidates
- Export candidate and benchmark reports

## Optimize-Rounds And Strategy-Benchmark

The current version does not directly rewrite `optimize-rounds` or `strategy-benchmark`. Their outputs can be adapted into `HistoryAdapter` and `CandidateAdapter` CSV inputs.

## Future Integration

Future work can add direct adapters for optimization_history.json, leaderboard.csv, and analysis_metrics.json. That work should preserve the current evidence boundary:

- data_source = real_simulation_csv
- engineering_validity = simulation_only

## Current Contract Status

The adapter contract exists. Deep closed-loop integration is not complete in this first version.
