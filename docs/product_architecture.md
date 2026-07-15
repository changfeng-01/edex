# CircuitPilot Product Architecture

CircuitPilot Route C keeps one evaluation and optimization kernel and exposes it through additive application surfaces.

## Surface ownership

- `src/goa_eval/web/` accepts uploads and runs the existing analysis pipeline.
- `src/goa_eval/web_api/` reads previously generated dashboard and product-demo artifacts.
- `src/goa_eval/product_api/` exposes persisted workspaces, projects, design versions, analyses, experiments, simulation jobs, comparisons, and read-only profiles.
- `src/goa_eval/product/` contains application services, repositories, immutable artifact storage, state transitions, adapters, and the ProfileService.
- Existing CLI commands remain direct kernel entrypoints and are not reimplemented in the product layer.

## Profile revision contract

ProfileService wraps `load_circuit_profiles` and freezes a validated revision into artifact storage. A revision records:

- canonical profile source hash and parameter-semantics hash;
- supported analyses and required metrics;
- node rules and normalized units;
- validation status and exact evidence boundary;
- an immutable snapshot artifact URI and checksum.

Validation rejects unknown semantic tags, aliases shared by multiple profiles, metrics sourced from unsupported analyses, invalid unit-bearing thresholds, and objective or hard-constraint references to missing metrics. The API is read-only until the schema is stable.

## General circuit adapters

OTA, comparator, and oscillator profiles use the existing generalized analysis interface. Metrics are accepted only when the current extractor supplies a value, unit, source file, source analysis, source column, parser, and normalization rule. Unsupported measurements such as phase margin, comparator kickback, and decision delay are not invented.

Adding a supported circuit type consists of a profile, semantic contract, deterministic end-to-end fixture, and regression tests. It does not add circuit-specific fields to Project, DesignVersion, Experiment, or Evidence.

## Trust boundary

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Candidate confirmation additionally requires an imported result checksum, a matching result design version, two completed analysis runs with matching boundaries, complete comparison evidence, and an improved verdict.
