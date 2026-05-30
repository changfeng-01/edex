# Multi-Agent Evidence Chain

CircuitPilot's multi-agent layer is an orchestration layer over the existing simulation evidence tools. It routes a task to domain agents, reads existing artifacts, records handoffs, runs critic checks, and writes a decision package. It does not replace the metric, scoring, optimizer, reporting, SKY130 sweep, or multi-round optimization modules.

The required boundary labels remain:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
```

The agent layer must preserve evidence metadata when it reads or summarizes artifacts: `evidence_level`, `simulation_backend`, `mock_used`, `pdk_available`, `ngspice_available`, `reportable_as_real_ngspice`, and `optimizer_claim_level`. A run with `mock_used=true` must not be reported as real ngspice evidence.

The multi-agent command is:

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/sky130_multi_agent_task.yaml \
  --output-dir outputs/multi_agent_sky130
```

## Agents

| Agent | Role |
| --- | --- |
| `SupervisorAgent` | Initializes shared state, plan metadata, and boundary context. |
| `RouterAgent` | Selects the domain path from task type, profile, and available inputs. |
| `GOAAgent` | Interprets GOA / 8T1C waveform artifacts, overlap, ripple, voltage loss, and false-trigger risk. |
| `SKY130Agent` | Interprets SKY130/ngspice evidence, score summaries, timing risk, and candidate context. |
| `GenericWaveformAgent` | Handles waveform-derived artifacts when no specific circuit family is selected. |
| `NetlistAgent` | Performs lightweight netlist integrity checks and reports parser limitations. |
| `EvaluationAgent` | Reads existing leaderboard, score summary, and real metrics artifacts. |
| `OptimizationAgent` | Calls existing optimizer wrappers to create bounded next candidates. |
| `CriticAgent` | Checks schema, boundary labels, hard constraints, metric missingness, false triggers, overlap/ripple risk, candidate risk, validation status, and forbidden physical-validation claims. |
| `ReportAgent` | Writes the final decision report and optimization evidence card. |

## Evidence Inputs

The layer can read current mainline artifacts by explicit path or by an `artifact_dir` / `run_dir` task input:

- `real_summary.json`
- `real_metrics.csv`
- `score_summary.json`
- `analysis_metrics.json`
- `diagnosis_report.md`
- `real_waveform_report.md`
- `next_candidates.csv`
- `best_next_candidates.csv`
- `optimization_history.json`
- `optimization_leaderboard.csv`
- `validation_summary.csv`
- `run_manifest_real.json`
- `sky130_mainline_report.md`
- `figures/figure_manifest.json`

`optimization_leaderboard.csv` is treated as the shared leaderboard when no task-specific `leaderboard` is supplied. `best_next_candidates.csv` is treated as the candidate table when no task-specific `next_candidates` is supplied.

`mainline_validation.json` and `validation_summary.csv` are the preferred sources for validation matrix rollups. Key fields are `validation_matrix_pass_rate`, `validation_case_count`, `validation_pass_count`, `validation_fail_count`, `validation_not_evaluable_count`, `worst_case_name`, `worst_case_metric`, and `worst_case_value`.

## Outputs

One run writes:

- `multi_agent_plan.json`
- `multi_agent_trace.jsonl`
- `multi_agent_handoff_trace.jsonl`
- `critic_report.json`
- `multi_agent_memory.json`
- `multi_agent_decision_report.md`
- `optimization_loop_record.json`
- `optimization_decision_card.md`

The optimization loop record stays rerun-aware. If candidate artifacts exist but rerun leaderboard, score, or metric artifacts are missing, the status remains `awaiting_rerun_results`; it must not be described as a completed physical optimization loop.

## Scope Boundary

This branch keeps multi-agent behavior first-class while preserving the existing simulation-data ingestion and SKY130/ngspice capabilities. The agents may inspect and summarize evidence, but they must not claim silicon validation, physical validation, tape-out proof, real chip verification, or industrial-grade full automation.

For real ngspice claims, the source artifact must have `reportable_as_real_ngspice=true`; otherwise the report should explicitly label the result as public/demo CSV, external CSV, or mock-ngspice evidence.
