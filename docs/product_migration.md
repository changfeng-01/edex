# CircuitPilot Product Migration

Phase 4 is additive. Existing CLI commands, upload cases, dashboard bundles, and Product API databases remain valid.

## Choose the correct surface

- Keep automation scripts on `python -m goa_eval.cli` when persistence and collaboration are unnecessary.
- Keep browser upload analysis on `goa_eval.web.app`.
- Keep existing generated dashboard bundles on `goa_eval.web_api`.
- Use `goa_eval.product_api.app` for persisted workspaces, approvals, simulation jobs, comparisons, and profile revision discovery.

No migration should copy scoring, recommendation, PIA, or simulator logic into the API layer.

## Existing projects and bundles

Existing projects retain the profile snapshot captured when they were created. New projects receive the current validated Profile revision; changing `config/circuit_profiles.yaml` does not rewrite old evidence. Existing product-demo bundles remain readable because `web_api` and the legacy `product-demo` CLI are unchanged.

The former OTA boundary value `real_simulation_artifacts` is historical data and is not silently rewritten. The stable `ota_general` aliases retain the Phase 3 metric contract; opt in to the measurable Phase 4 contract with `ota_general_v2` or `ota_v2`. New Profile API revisions and imported real-result records must declare the canonical boundary below exactly.

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

The CSVs under `examples/product_profiles/` are explicitly labelled `synthetic_fixture_csv / test_only`. They validate parsing and profile contracts only and cannot support an evaluated-improvement claim.

## Failure recovery

- Invalid Profile: run `GET /api/v1/profiles:validate`, fix every reported alias, semantic, analysis, metric, or unit error, then create a new project revision.
- Failed input preview: correct the uploaded waveform or parameter file; the failed preview does not create an analysis run.
- Interrupted manual simulation: keep the exported batch and submit results to the same simulation job. Preview before commit and preserve the manifest checksum.
- Invalid result contract: use the stable `RESULT_CONTRACT_INVALID` response, repair candidate IDs or parameter hashes, and retry the job. Invalid imports must not create result design versions.
- Interrupted PIA execution: resume the existing experiment; do not regenerate already persisted candidates or consume imported results twice.
- Insufficient comparison evidence: re-run analysis for both versions and confirm only after required evidence and matching boundaries are present.
- Unavailable simulator: return `adapter_unavailable`; switch to a configured adapter or export the manual contract.

Before release, run the full Python suite, frontend tests and build, the product demo builder, `git diff --check`, and review `origin/main..HEAD` for private or unrelated files.
