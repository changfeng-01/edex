from __future__ import annotations

import argparse
from pathlib import Path


def add_common_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default="config/evaluation_spec_low_voltage.yaml")
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

def output_path(args: argparse.Namespace) -> Path:
    if args.out:
        return Path(args.out)
    if args.command == "evaluate" and args.design:
        return Path("outputs")
    return Path("outputs/dev_run")
