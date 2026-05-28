# Multi-Agent Benchmark Suite

This suite checks that CircuitPilot routes tasks through the multi-agent evidence layer while preserving:

- data_source = real_simulation_csv
- engineering_validity = simulation_only

Each case contains:

- task.yaml
- expected.json
- README.md

Run:

```bash
python -m goa_eval.cli benchmark-run --suite benchmarks/multi_agent --output-dir outputs/benchmark_multi_agent
```
