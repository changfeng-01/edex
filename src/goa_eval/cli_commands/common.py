from __future__ import annotations

import argparse
from pathlib import Path


def add_common_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    parser.add_argument("--param-space", default="examples/sample_params.yaml")
    parser.add_argument("--circuit-profile")
    parser.add_argument("--profile-file")
    parser.add_argument("--params")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)


def add_csv_import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-dir", default=".")
    parser.add_argument("--output-dir", default="outputs/csv_import")
    add_common_profile_args(parser)


def add_empyrean_import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default="config/spec.yaml")
    parser.add_argument("--param-space", default="examples/sample_params.yaml")
    parser.add_argument("--circuit-profile")
    parser.add_argument("--profile-file")
    parser.add_argument("--params")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)


def add_sky130_common_args(parser: argparse.ArgumentParser, *, output_arg: str | None) -> None:
    parser.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    parser.add_argument("--split", choices=["train", "validation", "test"], default="train")
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--topology")
    parser.add_argument("--source-dataset")
    if output_arg:
        parser.add_argument(f"--{output_arg}", default="outputs/sky130_smoke")
    parser.add_argument("--ngspice-cmd", default="ngspice")
    parser.add_argument("--mock-dataset-json")
    parser.add_argument("--mock-ngspice", action="store_true")


def output_path(args: argparse.Namespace) -> Path:
    if args.out:
        return Path(args.out)
    if args.command == "evaluate" and args.design:
        return Path("outputs")
    return Path("outputs/dev_run")
