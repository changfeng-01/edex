# PIA-CA-LLSO Simulator Adapter Contract

The `pia-evolve` external simulator adapter is a command-template boundary for
real simulation tools such as Empyrean or SPICE wrappers.  It does not certify
physical, silicon, lab, or tapeout validation.

- data_source = real_simulation_csv
- engineering_validity = simulation_only

## Command Template

`pia-evolve --mode external_command --external-command "<template>"` replaces:

- `{candidate_csv}`: generated simulation batch CSV.
- `{result_csv}`: expected result CSV path, usually `simulation_results.csv`.
- `{generation}`: integer generation index.
- `{output_dir}`: generation artifact directory.

Each run writes:

- `simulator_invocation.json`
- `simulator_stdout.txt`
- `simulator_stderr.txt`

The adapter fails closed on non-zero exit, timeout, missing result file, or
result rows that do not match the pending simulation batch.

## Result CSV

Required columns:

- `candidate_id`
- `overall_score`
- `hard_constraint_passed`

Optional columns may include delay, power, waveform metrics, CAPM constraint
ledger fields, and simulator-specific diagnostics.  Extra columns are preserved
with validation warnings.  Candidate parameter columns must either be absent so
they can be recovered from the simulation batch, or exactly match the batch.

Imported result rows may set `must_resimulate = false`, but they remain
`engineering_validity = simulation_only`.
