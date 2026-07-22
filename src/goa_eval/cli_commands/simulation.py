from __future__ import annotations

import argparse
from pathlib import Path

from goa_eval.cli_commands.common import add_common_profile_args, add_csv_import_args
from goa_eval.csv_import_adapter import run_csv_import, run_csv_import_sweep


def register(subparsers: argparse._SubParsersAction) -> None:
    simulate_run = subparsers.add_parser("simulate-run")
    simulate_run.add_argument("--adapter", choices=["csv-import"], required=True)
    add_csv_import_args(simulate_run)
    simulate_run.set_defaults(handler=handle_simulate_run)

    simulate_sweep = subparsers.add_parser("simulate-sweep")
    simulate_sweep.add_argument("--adapter", choices=["csv-import"], required=True)
    simulate_sweep.add_argument("--input-root", default="outputs/csv_import_inputs")
    simulate_sweep.add_argument("--output-root", default="outputs/simulate_sweep")
    add_common_profile_args(simulate_sweep)
    simulate_sweep.set_defaults(handler=handle_simulate_sweep)


def handle_simulate_run(args: argparse.Namespace) -> int:
    run_csv_import(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        spec_path=Path(args.spec),
        param_space_path=Path(args.param_space),
        circuit_profile=args.circuit_profile,
        profile_file=Path(args.profile_file) if args.profile_file else None,
        params_file=Path(args.params) if args.params else None,
        max_candidates=args.max_candidates,
        seed=args.seed,
    )
    return 0


def handle_simulate_sweep(args: argparse.Namespace) -> int:
    run_csv_import_sweep(
        input_root=Path(args.input_root),
        output_root=Path(args.output_root),
        spec_path=Path(args.spec),
        param_space_path=Path(args.param_space),
        circuit_profile=args.circuit_profile,
        profile_file=Path(args.profile_file) if args.profile_file else None,
        params_file=Path(args.params) if args.params else None,
        max_candidates=args.max_candidates,
        seed=args.seed,
    )
    return 0
