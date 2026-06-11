# PIA-CA-LLSO API

## Standard History CSV

Recommended columns:

- `sample_id`
- parameter columns
- `overall_score`
- `hard_constraint_passed`
- `sim_success`
- `status`
- `source`

Rows with `status = predicted_only` are excluded from external benchmark evidence.

## Standard Candidate CSV

Recommended columns:

- `candidate_id`
- parameter columns
- optional `p_l1`
- optional `p_hard_pass`
- optional `predicted_score`
- optional `uncertainty`
- `source`

## Selected Candidate CSV

`pia_selected_candidates.csv` includes:

- `selected_rank`
- `candidate_role`
- `selection_reason`
- `acquisition_score`
- `acquisition_components_json`
- `diagnostic_status`

## Adapter Interface

`HistoryAdapter` and `CandidateAdapter` are CSV-first adapters. Future integration can map existing optimize-rounds or strategy outputs into these DataFrames.

## CLI Commands

- `pia-label`
- `pia-suggest`
- `pia-benchmark`
- `pia-export-contract`
