# Project Code Hardening Migration Guide

## Compatibility

Existing CLI command names, public optimizer imports, report filenames, and evidence labels remain unchanged:

- `data_source = real_simulation_csv`
- `engineering_validity = simulation_only`
- `must_resimulate = true`

Simulation-result imports now reject empty candidate IDs, non-finite scores, and ambiguous hard-constraint values. Accepted boolean values are `true`, `false`, `1`, `0`, `yes`, and `no` (case-insensitive).

## Waveform Coverage

Real-waveform summaries and manifests now include `expected_stage_count`, `observed_stage_count`, `output_coverage_ratio`, `coverage_status`, `missing_output_nodes`, and `full_cascade_claim_allowed`.

Exploratory CLI runs retain partial-node compatibility and label the result `partial`. Use `evaluate-real --strict-output-coverage` to reject partial coverage. Web analysis also rejects partial coverage when `stage_count` is supplied.

## External Simulator Commands

Prefer argv configuration so paths are passed without a shell:

```yaml
simulation_executor:
  mode: external_command
  external_command_argv:
    - python
    - simulator_driver.py
    - "{candidate_csv}"
    - "{result_csv}"
    - "{generation}"
    - "{output_dir}"
  allow_shell_command: false
```

The legacy `external_command` string remains available for trusted local runs. Formal configurations should set `allow_shell_command: false`. Invocation evidence records the executable, working directory, legacy-shell flag, stdout/stderr, exit status, and result-validation status.

## Web Write Security

Set `CIRCUITPILOT_WRITE_API_KEY` and `CIRCUITPILOT_REQUIRE_WRITE_AUTH=true` for deployed write APIs. POST clients send `Authorization: Bearer <key>`. The browser upload UI stores an operator-entered key in `sessionStorage`; no write key is compiled into the frontend bundle.

Case IDs are create-only. Reusing an existing ID returns HTTP 409 and never replaces existing data. Preview calls always receive a generated temporary ID and do not seed the later analysis ID.

Default upload limits are 64 MiB for waveform/netlist files, 2 MiB for parameters, 16 MiB per image, 128 MiB total, and 10 attachments. The corresponding `CIRCUITPILOT_MAX_*` variables are listed in `.env.example`.

## Local Waveform Diagnostic Integration Checklist

The uncommitted `waveform_diagnostic_training.py` work from the parent workspace was intentionally excluded. Before integrating it later:

1. Rebase or merge this branch without copying `.trae/`, `cgg_v1/`, generated reports, or paper drafts.
2. Route imported hard-constraint values through `pia_ca_llso.value_coercion.strict_bool`.
3. Preserve the exact evidence labels in generated CSV, JSON, and Markdown outputs.
4. Add expected/observed stage coverage when the diagnostic consumes sampled waveform nodes.
5. Run its focused tests, `python -m pytest tests -k "pia or waveform" -q`, Ruff, and the full suite before publishing.
