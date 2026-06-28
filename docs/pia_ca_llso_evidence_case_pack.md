# PIA-CA-LLSO Evidence Case Pack

Phase 4 case packs make a GOA scenario auditable from inputs through publication tables. A pack contains:

- `scenario.yaml`
- `history.csv`
- `candidate_pool.csv`
- `simulation_results.csv`
- `scoring_config.yaml`
- `provenance.json`

The candidate pool is pre-simulation input and must not include `overall_score`, `hard_constraint_passed`, waveform metrics, or other imported-result fields. Missing `simulation_results.csv` is allowed only for selection-only planning unless `--strict-evidence` is disabled.

Required boundary labels must remain verbatim:

- data_source = real_simulation_csv
- engineering_validity = simulation_only
- must_resimulate = true

Run validation with:

```bash
python -m goa_eval.cli pia-validate --case-pack-root examples/pia_ca_llso/case_packs --output-dir outputs/pia_case_pack_validation --strict-evidence
```

The generated `source_lock.json` records input hashes, command arguments, Python version, git commit, generation time, and the same evidence boundary labels. These reports are simulation-only evidence, not physical validation.
