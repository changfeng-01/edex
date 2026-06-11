from __future__ import annotations

from goa_eval.cli import build_parser


COMMAND_ARGV = {
    "extract": ["extract"],
    "parse": ["parse"],
    "evaluate": ["evaluate"],
    "all": ["all"],
    "evaluate-real": ["evaluate-real", "--waveform", "waveform.csv"],
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
    "sky130-transient": ["sky130-transient"],
    "sky130-sweep": ["sky130-sweep"],
    "optimize-rounds": ["optimize-rounds"],
    "sky130-mainline": ["sky130-mainline"],
    "strategy-benchmark": ["strategy-benchmark"],
    "hybrid-goa-optimize": ["hybrid-goa-optimize"],
    "goa-strategy-benchmark": ["goa-strategy-benchmark"],
    "eclipse-benchmark": ["eclipse-benchmark"],
    "pia-label": ["pia-label", "--history-csv", "history.csv", "--output-dir", "out"],
    "pia-suggest": ["pia-suggest", "--history-csv", "history.csv", "--candidate-csv", "candidates.csv", "--output-dir", "out"],
    "pia-benchmark": ["pia-benchmark", "--history-csv", "history.csv", "--candidate-csv", "candidates.csv", "--output-dir", "out"],
    "pia-export-contract": ["pia-export-contract", "--output-dir", "out"],
    "pia-train-from-db": ["pia-train-from-db"],
}


def test_all_public_subcommands_have_handlers() -> None:
    parser = build_parser()

    for command, argv in COMMAND_ARGV.items():
        args = parser.parse_args(argv)
        assert args.command == command
        assert callable(args.handler)
