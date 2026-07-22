from __future__ import annotations

from goa_eval.cli import build_parser


COMMAND_ARGV = {
    "extract": ["extract"],
    "parse": ["parse"],
    "evaluate": ["evaluate"],
    "all": ["all"],
    "evaluate-real": ["evaluate-real", "--waveform", "waveform.csv"],
    "train-waveform-diagnostic": ["train-waveform-diagnostic", "--waveform", "waveform.csv"],
    "recommend": ["recommend", "--summary", "real_summary.json"],
    "product-demo": ["product-demo", "--input-dir", "case", "--case-id", "demo"],
    "demo": ["demo"],
    "evaluate-batch": ["evaluate-batch", "--runs-dir", "runs"],
    "multi-agent-run": ["multi-agent-run", "--task", "task.yaml", "--output-dir", "out"],
    "benchmark-run": ["benchmark-run", "--suite", "suite", "--output-dir", "out"],
    "propose-candidates": ["propose-candidates", "--summary", "summary.json", "--param-space", "params.yaml"],
    "validate-config": ["validate-config", "--profile-file", "profile.yaml"],
    "analyze-params": ["analyze-params", "--summary", "summary.json"],
    "ai-profile-assistant": ["ai-profile-assistant", "--description", "description.md"],
    "csv-import": ["csv-import"],
    "empyrean-import": ["empyrean-import", "--case-id", "demo"],
    "simulate-run": ["simulate-run", "--adapter", "csv-import"],
    "simulate-sweep": ["simulate-sweep", "--adapter", "csv-import"],
    "hybrid-goa-optimize": ["hybrid-goa-optimize"],
    "goa-strategy-benchmark": ["goa-strategy-benchmark"],
    "eclipse-benchmark": ["eclipse-benchmark"],
    "pia-label": ["pia-label", "--history-csv", "history.csv", "--output-dir", "out"],
    "pia-suggest": ["pia-suggest", "--history-csv", "history.csv", "--candidate-csv", "candidates.csv", "--output-dir", "out"],
    "pia-benchmark": ["pia-benchmark", "--history-csv", "history.csv", "--candidate-csv", "candidates.csv", "--output-dir", "out"],
    "pia-export-contract": ["pia-export-contract", "--output-dir", "out"],
    "pia-render-transistor-netlists": ["pia-render-transistor-netlists", "--simulation-batch", "batch.csv", "--template", "template.spice", "--output-dir", "out"],
    "pia-train-from-db": ["pia-train-from-db"],
    "pia-evolve": ["pia-evolve", "--history-csv", "history.csv", "--candidate-csv", "candidates.csv", "--config", "config.yaml", "--output-dir", "out"],
    "pia-validate": ["pia-validate", "--protocol", "protocol.yaml", "--output-dir", "out"],
}


def test_all_public_subcommands_have_handlers() -> None:
    parser = build_parser()

    for command, argv in COMMAND_ARGV.items():
        args = parser.parse_args(argv)
        assert args.command == command
        assert callable(args.handler)


def test_retired_sky130_commands_and_adapters_are_not_registered() -> None:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )
    for command in {
        "sky130-transient",
        "sky130-sweep",
        "optimize-rounds",
        "sky130-mainline",
        "strategy-benchmark",
    }:
        assert command not in subparsers.choices

    for command in ("simulate-run", "simulate-sweep"):
        command_parser = subparsers.choices[command]
        adapter_action = next(action for action in command_parser._actions if action.dest == "adapter")
        assert tuple(adapter_action.choices) == ("csv-import",)
