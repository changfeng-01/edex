# Metrics Specification

This document defines the current CircuitPilot metric semantics. All values are derived from simulation CSV files and remain `simulation_only`.

## Window Terms

- `legal_windows`: high-level pulse windows whose duration is at least `min_pulse_width`.
- `primary_window`: the first legal pulse window.
- `repeated_windows`: later legal pulse windows in the same waveform; these are legal repeated scans, not false triggers.
- `selected_window`: the center region of the primary window used for VOH and hold-end estimates.
- `hold / non-selected window`: samples outside all legal pulse windows plus an edge buffer.

## Stage Metrics

| Field | Unit | Definition |
|---|---:|---|
| `PulseExist` | bool | True when a legal high pulse exists. |
| `LegalPulseCount` | count | Number of legal pulse windows. |
| `VOH_mean` | V | Mean voltage inside the selected center of the primary pulse. |
| `VOH_max` | V | Maximum voltage inside the selected center of the primary pulse. |
| `VHoldEnd` | V | Last finite value inside the selected center of the primary pulse. |
| `VoltageLoss` | V | `max(0, VOH_max - VHoldEnd)`. |
| `VoltageLossRatio` | ratio | `VoltageLoss / VOH_max` when `VOH_max` is nonzero. |
| `VOL_max` | V | Maximum voltage in the hold / non-selected window. |
| `PulseWidth` | s | `primary_window.end - primary_window.start`. |
| `Delay` | s | Difference between adjacent stages' rising threshold crossing times. |
| `RiseTime` | s | 10% to 90% edge duration estimate. |
| `FallTime` | s | 90% to 10% edge duration estimate. |
| `Ripple` | V | `max(signal) - min(signal)` inside hold / non-selected windows only. |
| `FalseTriggerCount` | count | Number of non-selected high windows after excluding all legal pulses and edge buffers. |
| `Overlap` | s | Sum of adjacent legal-window intersections by interval endpoints. |
| `OverlapRatio` | ratio | `Overlap / min(left PulseWidth, right PulseWidth)`. |

## Parameter Metadata

Batch evaluation joins metrics with `params.yaml` metadata. Parameters such as `C_store`, `R_driver`, `W_pmos`, `W_nmos`, `VDD`, and `load_cap` do not change metric definitions; they make the output table usable for later comparison, ranking, and recommendation.

## Important Policies

- Ripple excludes rising and falling edges by removing legal pulse windows plus an edge buffer.
- Repeated periodic scan pulses are legal windows and must not be counted as false triggers.
- Overlap uses endpoint interval integration, not average sample-step estimation. This avoids distortion under nonuniform sampling.
- `LowFreqStable` is `not_evaluable_with_current_waveform` when waveform duration is shorter than the target frame hold time.
- `PASS_BASIC_SIMULATION_CHECK` only means the configured simulation CSV checks pass. It does not imply a physical product or lab result has passed.

## Recommendation Use

Recommendation rules may inspect metrics such as `Max_overlap_ratio`, `Max_ripple`, `Delay_mean`, `FalseTriggerCount`, and `LowFreqStable`. The recommendation text is a next-round engineering suggestion, not an automatic optimization result.
