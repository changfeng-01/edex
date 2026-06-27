# PIA-CA-LLSO Real Simulation Case Pack

A real simulation case pack supplies externally generated simulator CSV evidence for Phase 3 validation. It is still simulation-only evidence and must not be described as silicon, lab, hardware, tapeout, or physical validation.

Required manifest fields:

- `scenario_id`
- `source_type: real_simulation_csv`
- `history_csv`
- `candidate_csv`
- `result_dirs`
- `config`
- `boundary.data_source: real_simulation_csv`
- `boundary.engineering_validity: simulation_only`
- `boundary.must_resimulate: true`

Paper-digitized or local fixture rows must not be marked as `real_simulation_csv` case packs.
