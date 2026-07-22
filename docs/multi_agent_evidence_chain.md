# Multi-Agent Evidence Chain

CircuitPilot's multi-agent layer routes a task to a registered circuit-domain
agent and then reuses shared evaluation, transfer, optimization, critic, memory,
and reporting services. Circuit-specific equations live in a
`DomainPhysicsAdapter`; orchestration and numerical projection remain shared.

The required external-simulation boundary labels are:

```text
data_source = real_simulation_csv
engineering_validity = simulation_only
must_resimulate = true
```

Analytic-only instrumentation-amplifier output is instead labeled
`data_source = analytic_model_proxy`. It is diagnostic evidence and cannot be
promoted to a real-simulation candidate.

## Registered domain agents

| Agent | Role |
| --- | --- |
| `GOAAgent` | GOA/TFT waveform and local electrical diagnosis. |
| `InstrumentationAmplifierAgent` | Three-op-amp instrumentation-amplifier MNA, PVT, task-head, and sensitivity analysis. |
| `GenericWaveformAgent` | Waveform artifacts without a more specific circuit profile. |
| `NetlistAgent` | Generic netlist integrity and parser diagnostics. |

`DomainAgentRegistry` resolves an exact profile first, then an alias, task type,
and finally the input-type fallback. Core contracts are merged with registry
contracts, so adding another circuit family does not require a new hard-coded
router branch.

## Execution paths

Without a source effect packet:

```text
Supervisor -> Router -> Domain Agent -> Critic -> Evaluation
           -> Optimization -> Critic -> Report
```

With a source effect packet:

```text
Supervisor -> Router -> Domain Agent -> Critic -> Evaluation
           -> TransferCoordinator -> Critic -> Optimization
           -> Critic -> Report
```

The coordinator operates only on supported canonical physical effects. Missing
and not-applicable effects are never replaced with zeros. Projection is rejected
for rank loss, poor conditioning, excessive normalized uncertainty, excessive
residual, or insufficient effect alignment.

## Three-op-amp example

```bash
python -m goa_eval.cli multi-agent-run \
  --task examples/tasks/instrumentation_amplifier_agent_task.yaml \
  --output-dir outputs/instrumentation_amplifier_agent
```

The project does not execute a local circuit simulator. It imports external CSV
evidence through the generic simulation adapter and exports bounded candidates
for a later simulation run.

## Artifacts

Common artifacts retain their existing names, including the plan, trace,
handoff, critic, memory, candidates, and final report. The instrumentation and
transfer path additionally writes:

- `instrumentation_agent_diagnosis.json`
- `physical_effect_packet.json`
- `target_sensitivity.json`
- `transfer_projection.json` when a projection is accepted

An external CSV row is keyed by `sample_id` and a scenario key formed from
`corner + temperature_c + supply`. Every scenario is evaluated independently;
the score combines 50% weighted mean and 50% worst case, while the barrier is
the scenario maximum.

## Scope boundary

The agents organize simulation evidence and propose the next simulation inputs.
They do not establish silicon validation, laboratory validation, tape-out proof,
or a completed optimization result. A candidate remains a next-run suggestion
until the external simulator returns new evidence.
