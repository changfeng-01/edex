from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.normalize_waveform import load_curve_map, normalize_wpd_frame, parse_duration
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_CLAIM_BOUNDARY,
    SOURCE_TYPE_PAPER_DIGITIZED,
)


def convert_wpd_csv(
    *,
    input_path: Path,
    output_path: Path,
    time_unit: str = "s",
    voltage_unit: str = "V",
    curve_map_path: Path | None = None,
    resample_step: str | None = None,
    quality_path: Path | None = None,
) -> dict:
    raw = pd.read_csv(input_path)
    normalized = normalize_wpd_frame(
        raw,
        time_unit=time_unit,
        voltage_unit=voltage_unit,
        curve_map=load_curve_map(curve_map_path),
        resample_step=parse_duration(resample_step),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.frame.to_csv(output_path, index=False, encoding="utf-8-sig")
    quality = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
        "weak_label": True,
        "engineering_validity": ENGINEERING_VALIDITY,
        "claim_boundary": PAPER_CLAIM_BOUNDARY,
        **normalized.quality,
    }
    write_json(quality_path or output_path.parent / "digitization_quality.json", quality)
    return quality


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert WebPlotDigitizer CSV to CircuitPilot waveform.csv.")
    parser.add_argument("--input", dest="input_path", type=Path, required=True)
    parser.add_argument("--output", dest="output_path", type=Path, required=True)
    parser.add_argument("--time-unit", default="s")
    parser.add_argument("--voltage-unit", default="V")
    parser.add_argument("--curve-map", dest="curve_map_path", type=Path)
    parser.add_argument("--resample-step")
    parser.add_argument("--quality-output", dest="quality_path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    quality = convert_wpd_csv(
        input_path=args.input_path,
        output_path=args.output_path,
        time_unit=args.time_unit,
        voltage_unit=args.voltage_unit,
        curve_map_path=args.curve_map_path,
        resample_step=args.resample_step,
        quality_path=args.quality_path,
    )
    print(quality["output_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
