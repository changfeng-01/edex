# CircuitPilot Project Overview

CircuitPilot / 芯智调参 is a simulation-driven circuit evaluation, diagnosis, and rule-based parameter recommendation prototype. The Python package name remains `goa_eval` for compatibility with the existing GOA waveform evaluation workflow.

## Current Boundary

All real waveform outputs must keep:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

The project does not claim physical validation, does not call an external SPICE simulator in the current version, and does not implement a complete automatic closed-loop circuit optimization system.

## Current Workflow

1. Read real or example simulation waveform CSV files.
2. Normalize waveform columns such as `XVAL`, `TIME`, `v(o1)`, `v(o2)`, and `v(xs4.pu)`.
3. Detect legal output pulse windows for `o1~oN`.
4. Compute timing, voltage, overlap, ripple, false-trigger, and hold-loss metrics.
5. Score the run using separated hard constraints and soft scores.
6. Generate CSV / JSON / Markdown / PNG reports.
7. Generate conservative rule recommendations for the next parameter review round.

## Main Commands

Single waveform evaluation:

```bash
python -m goa_eval.cli evaluate-real --waveform examples/sample_waveform.csv --output-dir outputs/example
```

Single-run recommendation:

```bash
python -m goa_eval.cli recommend --summary outputs/example/real_summary.json --score outputs/example/score_summary.json --metrics outputs/example/real_metrics.csv --output outputs/example/recommendations.md
```

Batch evaluation:

```bash
python -m goa_eval.cli evaluate-batch --runs-dir runs --output-dir outputs_batch
```

## Batch Run Convention

```text
runs/
├── run_001/
│   ├── params.yaml
│   └── waveform.csv
└── run_002/
    ├── params.yaml
    └── waveform.csv
```

`params.yaml` stores design parameters and simulation conditions:

```yaml
run_id: run_001
circuit_version: goa_8t1c_v1
parameters:
  C_store: 1pF
  R_driver: 10k
  W_pmos: 2u
  W_nmos: 1u
  VDD: 15
  load_cap: 5pF
conditions:
  temp: 25
  corner: TT
```

## Extension Direction

The intended development path is:

1. stabilize schemas and metric definitions;
2. collect multiple parameter-result runs;
3. improve rule-based recommendations;
4. add parameter-space candidate generation;
5. only after enough data exists, evaluate Bayesian optimization, evolutionary algorithms, or machine-learning models.
