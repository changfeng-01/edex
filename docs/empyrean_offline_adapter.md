# Empyrean FPD Offline Adapter

`empyrean-import` is an offline import adapter for exported Huada Jiutian / Empyrean FPD files. It reads files that the user has already exported and converts the waveform portion into the normal CircuitPilot evaluation flow.

It does not start, automate, or replace EsimFPD Model, AetherFPD SE/LE, ArgusFPD, ALPSFPD, iWaveFPD, or RCExplorerFPD.

## Supported exported files

Recommended input layout:

```text
examples/empyrean_case/
  simulation/waveform.csv
  verification/drc_report.txt
  verification/lvs_report.txt
  verification/erc_report.txt
  rc/rc_result.csv
  model/model.sp
  schematic/netlist.sp
  layout/layer_summary.json
  params.yaml
```

Flat layouts are also accepted when common file names are present in the case root.

The adapter recognizes:

- ALPSFPD / iWaveFPD waveform CSV exports.
- ArgusFPD DRC, LVS, ERC, and PVE reports in text, report, log, or CSV-like files.
- RCExplorerFPD RC result CSV or simple text tables.
- EsimFPD model files such as `.sp`, `.spi`, `.mod`, `.model`, and `.txt`.
- Schematic and layout metadata files for manifest registration.

## Command

```bash
python -m goa_eval.cli empyrean-import \
  --input-dir examples/empyrean_case \
  --output-dir outputs/empyrean_case \
  --case-id demo_empyrean_case \
  --generate-candidates
```

Optional controls include `--spec`, `--param-space`, `--stage-count`, `--output-node-pattern`, `--topology`, `--circuit-profile`, `--profile-file`, `--params`, `--max-candidates`, and `--seed`.

## Outputs

The output directory contains the normal CircuitPilot evaluation artifacts plus Empyrean-specific import evidence:

```text
normalized_waveform.csv
waveform_column_map.json
empyrean_case_manifest.json
physical_verification_summary.json
parasitic_summary.json
model_artifact_summary.json
empyrean_interface_manifest.json
real_summary.json
score_summary.json
real_metrics.csv
real_waveform_report.md
diagnosis_report.md
recommendations.md
next_candidates.csv / next_candidates.md
```

Candidate files are only written when `--generate-candidates` is set.

## Interface manifest

`empyrean_interface_manifest.json` is the stable interface contract for the exported Empyrean FPD case. It does not prove the design is correct and it does not invoke the EDA tools. It records the file-level contracts that must line up before CircuitPilot can make useful next-run simulation suggestions:

- `port_contract`: schematic and waveform signal names, with roles such as input stimulus, output observation, common electrode, power, and ground. Final LVS should compare top ports; ignoring layout/source top ports is treated as debug-only.
- `model_contract`: model card names found in EsimFPD-style model files and model or subcircuit names referenced by schematic netlists.
- `stimulus_contract`: normalized waveform signals and the recommended ALPSFPD stimulus fields for `vpulse` / `vpwl` style reruns.
- `verification_gate_contract`: DRC, LVS, and ERC status as blocking gates for engineering claims.
- `parasitic_contract`: RCExplorer-derived critical nets with resistance/capacitance summaries that can feed optimizer context.
- `layout_contract`: layout metadata artifacts such as layer summaries, GDS, technology files, and layer maps when provided.

The interface manifest keeps the manual workflow explicit:

```text
EsimFPD Model export -> model_contract
AetherFPD schematic/layout export -> port_contract and layout_contract
ArgusFPD DRC/LVS/ERC reports -> verification_gate_contract
RCExplorerFPD result export -> parasitic_contract
ALPSFPD/iWaveFPD waveform export -> stimulus_contract
```

All optimizer outputs remain next-run simulation suggestions. After changing parameters, the user must rerun ALPSFPD simulation, ArgusFPD verification, and RCExplorerFPD extraction before reporting an engineering improvement.

## Evidence boundary

The manifest records:

```text
toolchain = empyrean_fpd_offline
execution_mode = offline_import_only
tool_invocation = false
data_source = exported_empyrean_files
engineering_validity = simulation_or_tool_export_only
must_resimulate = true
no_local_empyrean_tool_invocation = true
not_silicon_validated = true
```

DRC passed only means the imported DRC report states that DRC passed. LVS passed only means the imported LVS report states that layout and schematic matched. ERC passed only means the imported ERC report states that no electrical rule failure was reported. Missing reports are `not_provided`; ambiguous reports are `unknown`.

All parameter suggestions remain next-run simulation suggestions. A candidate must be re-simulated, re-verified, and re-extracted in the real EDA flow before it can be discussed as an engineering improvement.

## Future extension

If a future environment has licensed local Empyrean tools, a separate `empyrean-run` or `empyrean-sweep` command can be added. That command should stay separate from `empyrean-import` and must keep explicit tool availability, command provenance, and evidence-level fields.
