from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import write_recommendations_markdown


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    waveform = args.waveform
    output_dir = args.output_dir
    spec = args.config

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=output_dir,
        spec_path=spec,
    )
    write_recommendations_markdown(
        summary_path=output_dir / "real_summary.json",
        score_path=output_dir / "score_summary.json",
        metrics_path=output_dir / "real_metrics.csv",
        output_path=output_dir / "recommendations.md",
    )

    print(f"Public demo waveform: {waveform.as_posix()}")
    print(f"Output directory: {output_dir.as_posix()}")
    print("Generated:")
    for name in [
        "real_summary.json",
        "score_summary.json",
        "real_metrics.csv",
        "optimization_dataset.csv",
        "diagnosis_report.md",
        "real_waveform_report.md",
        "recommendations.md",
        "run_manifest_real.json",
    ]:
        print(f"- {name}")
    print("Boundary: data_source=real_simulation_csv, engineering_validity=simulation_only")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the public CircuitPilot reproducibility demo.")
    parser.add_argument("--waveform", type=Path, default=Path("examples/sample_waveform.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/public_demo"))
    parser.add_argument("--config", type=Path, default=Path("config/spec.yaml"))
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
