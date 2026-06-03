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
real_summary.json
score_summary.json
real_metrics.csv
real_waveform_report.md
diagnosis_report.md
recommendations.md
next_candidates.csv / next_candidates.md
```

Candidate files are only written when `--generate-candidates` is set.

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
