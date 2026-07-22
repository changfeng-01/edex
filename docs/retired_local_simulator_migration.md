# SKY130/ngspice Removal Migration Note

This is the sole migration record for the removed SKY130/ngspice integration.
The runtime modules, specialized commands, adapter, agent, configurations,
examples, dependency group, and dedicated tests were removed from the project.

The generic commands remain compatible:

- `simulate-run --adapter csv-import`
- `simulate-sweep --adapter csv-import`

The simulator registry and offline/manual task contracts remain available for
other adapters. Product database rows are not migrated or deleted. A historical
row containing the retired adapter identifier remains readable, but attempting
to execute it returns the stable reason `adapter_unavailable`.

Legacy JSON input may contain the former PDK/backend availability extensions.
Readers tolerate those unknown fields and do not emit them in current evidence
output. External CSV evidence uses `evidence_level=level_1_external_csv` and
`simulation_backend=external_csv`.

No other public CLI, Product API, database schema, GOA/TFT metric version, or
generic netlist and waveform capability is intentionally removed by this
migration.
