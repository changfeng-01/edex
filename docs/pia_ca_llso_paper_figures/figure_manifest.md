# PIA-CA-LLSO Paper Figure Manifest

This package contains publication-preparation figures for the PIA-CA-LLSO manuscript.

Evidence boundary fixed for every figure:

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

## Data Sources

- Formal method definition: `docs/pia_ca_llso_formal_method_zh.md`
- Sample history: `examples/pia_ca_llso/sample_history.csv`
- Sample candidates: `examples/pia_ca_llso/sample_candidates.csv`
- Sample simulation results: `examples/pia_ca_llso/case_packs/sample_goa/simulation_results.csv`
- Validation summary: `not_found`
- Ablation summary: `outputs/pia_capm_benchmark/pia_ablation_summary.json`
- Selected candidates: `outputs/pia_capm_suggest/pia_selected_candidates.csv`

## Figure Entries

| Figure | File | Evidence role | Supports | Does not support |
|---|---|---|---|---|
| Fig. 1 | `figures/fig01_graphical_abstract.png` | Conceptual schematic; GPT image2 prompt recorded and deterministic labels rendered locally | Overall closed-loop workflow and terminology alignment | Physical silicon validation, tapeout validation, or measured lab performance |
| Fig. 2 | `figures/fig02_closed_loop_architecture.png` | Conceptual schematic | Module boundary of labeling, LLSO, selection, simulation import, and audit | Claim that every simulator backend has been experimentally validated |
| Fig. 3 | `figures/fig03_capm_physics_manifold.png` | Conceptual schematic | CAPM-Distance idea: physics features, L1 basin, barrier proxy, geodesic path, missingness | Claim that barrier proxy equals real hard-constraint failure |
| Fig. 4 | `figures/fig04_acquisition_ensemble.png` | Conceptual schematic | Acquisition ensemble composition and five-paper-inspired extension layer | Full reproduction of DEAOE, HRCEA, AIEA, CESAEA, or ECCoEA-ASAA |
| Fig. 5 | `figures/fig05_strategy_benchmark.png` | sample/smoke visualization; not full validation evidence | Available benchmark/evidence fields and boundary audit | Final method superiority without Phase 3 validation CSV |
| Fig. 6 | `figures/fig06_ablation_and_boundary.png` | sample/smoke visualization; not full validation evidence | Boundary pass status and deferred formal validation slots | Numeric ablation conclusions if formal validation CSV is absent |
| Fig. 7 | `figures/fig07_candidate_acquisition_diagnostics.png` | Candidate suggestion diagnostics from CSV where available | Why top candidates were suggested for next-run simulation | That suggestions are already physical validation evidence |

## Generated Files

- `docs/pia_ca_llso_paper_figures/figures/fig01_graphical_abstract.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig01_graphical_abstract.png`
- `docs/pia_ca_llso_paper_figures/figures/fig02_closed_loop_architecture.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig02_closed_loop_architecture.png`
- `docs/pia_ca_llso_paper_figures/figures/fig03_capm_physics_manifold.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig03_capm_physics_manifold.png`
- `docs/pia_ca_llso_paper_figures/figures/fig04_acquisition_ensemble.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig04_acquisition_ensemble.png`
- `docs/pia_ca_llso_paper_figures/figures/fig05_strategy_benchmark.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig05_strategy_benchmark.png`
- `docs/pia_ca_llso_paper_figures/figures/fig06_ablation_and_boundary.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig06_ablation_and_boundary.png`
- `docs/pia_ca_llso_paper_figures/figures/fig07_candidate_acquisition_diagnostics.pdf`
- `docs/pia_ca_llso_paper_figures/figures/fig07_candidate_acquisition_diagnostics.png`
- `docs/pia_ca_llso_paper_figures/prompts/image2_prompts.json`
