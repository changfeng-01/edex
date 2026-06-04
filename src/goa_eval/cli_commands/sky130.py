from __future__ import annotations

import argparse
import sys
from pathlib import Path

from goa_eval.cli_commands.common import add_common_profile_args, add_csv_import_args, add_sky130_common_args
from goa_eval.csv_import_adapter import run_csv_import, run_csv_import_sweep
from goa_eval.multi_round_optimizer import run_multi_round_optimization
from goa_eval.sky130_mainline import run_sky130_mainline
from goa_eval.sky130_sweep import run_sky130_sweep
from goa_eval.sky130_transient import Sky130DependencyError, run_sky130_transient
from goa_eval.strategy_benchmark import parse_seeds, run_strategy_benchmark


def register(subparsers: argparse._SubParsersAction) -> None:
    register_simulation_adapter_commands(subparsers)
    register_sky130_run_commands(subparsers)
    register_optimization_commands(subparsers)


def register_simulation_adapter_commands(subparsers: argparse._SubParsersAction) -> None:
    simulate_run = subparsers.add_parser("simulate-run")
    simulate_run.add_argument("--adapter", choices=["csv-import", "sky130-transient"], required=True)
    add_csv_import_args(simulate_run)
    add_sky130_common_args(simulate_run, output_arg=None)
    simulate_run.set_defaults(handler=handle_simulate_run)

    simulate_sweep = subparsers.add_parser("simulate-sweep")
    simulate_sweep.add_argument("--adapter", choices=["csv-import", "sky130-sweep"], required=True)
    simulate_sweep.add_argument("--input-root", default="outputs/csv_import_inputs")
    simulate_sweep.add_argument("--output-root", default="outputs/simulate_sweep")
    simulate_sweep.add_argument("--sweep", default="config/sky130_sweep.yaml")
    simulate_sweep.add_argument("--pdk-root")
    simulate_sweep.add_argument("--max-runs", type=int)
    add_common_profile_args(simulate_sweep)
    add_sky130_common_args(simulate_sweep, output_arg=None)
    simulate_sweep.set_defaults(handler=handle_simulate_sweep)


def register_sky130_run_commands(subparsers: argparse._SubParsersAction) -> None:
    sky130 = subparsers.add_parser("sky130-transient")
    sky130.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    sky130.add_argument("--split", choices=["train", "validation", "test"], default="train")
    sky130.add_argument("--max-rows", type=int, default=5)
    sky130.add_argument("--topology")
    sky130.add_argument("--source-dataset")
    sky130.add_argument("--output-root", default="outputs/sky130_smoke")
    sky130.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    sky130.add_argument("--param-space", default="examples/sample_params.yaml")
    sky130.add_argument("--max-candidates", type=int, default=10)
    sky130.add_argument("--seed", type=int, default=42)
    sky130.add_argument("--ngspice-cmd", default="ngspice")
    sky130.add_argument("--mock-dataset-json")
    sky130.add_argument("--mock-ngspice", action="store_true")
    sky130.add_argument("--skip-netlist-structure", action="store_true")
    sky130.set_defaults(handler=handle_sky130_transient)

    sweep = subparsers.add_parser("sky130-sweep")
    sweep.add_argument("--sweep", default="config/sky130_sweep.yaml")
    sweep.add_argument("--pdk-root")
    sweep.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    sweep.add_argument("--split", choices=["train", "validation", "test"], default="train")
    sweep.add_argument("--max-rows", type=int, default=5)
    sweep.add_argument("--topology")
    sweep.add_argument("--source-dataset")
    sweep.add_argument("--output-root", default="outputs/sky130_sweep")
    sweep.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    sweep.add_argument("--param-space", default="examples/sample_params.yaml")
    sweep.add_argument("--max-candidates", type=int, default=10)
    sweep.add_argument("--seed", type=int, default=42)
    sweep.add_argument("--max-runs", type=int)
    sweep.add_argument("--ngspice-cmd", default="ngspice")
    sweep.add_argument("--mock-dataset-json")
    sweep.add_argument("--mock-ngspice", action="store_true")
    sweep.set_defaults(handler=handle_sky130_sweep)


def register_optimization_commands(subparsers: argparse._SubParsersAction) -> None:
    optimize = subparsers.add_parser("optimize-rounds")
    optimize.add_argument("--sweep", default="config/sky130_sweep.yaml")
    optimize.add_argument("--pdk-root")
    optimize.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    optimize.add_argument("--split", choices=["train", "validation", "test"], default="train")
    optimize.add_argument("--max-rows", type=int, default=5)
    optimize.add_argument("--topology")
    optimize.add_argument("--source-dataset")
    optimize.add_argument("--output-root", default="outputs/sky130_multi_round")
    optimize.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    optimize.add_argument("--param-space", default="examples/sample_params.yaml")
    optimize.add_argument("--max-candidates", type=int, default=10)
    optimize.add_argument("--seed", type=int, default=42)
    optimize.add_argument("--rounds", type=int, default=3)
    optimize.add_argument("--strategy", choices=["random", "adaptive", "genetic", "bayesian", "surrogate", "repair", "hybrid", "hybrid_goa", "physics_guided_hybrid"], default="adaptive")
    optimize.add_argument("--max-runs-per-round", type=int, default=5)
    optimize.add_argument("--patience", type=int, default=2)
    optimize.add_argument("--min-improvement", type=float, default=0.0)
    optimize.add_argument("--exploration-ratio", type=float, default=0.25)
    optimize.add_argument("--validation-config")
    optimize.add_argument("--ngspice-cmd", default="ngspice")
    optimize.add_argument("--mock-dataset-json")
    optimize.add_argument("--mock-ngspice", action="store_true")
    optimize.set_defaults(handler=handle_optimize_rounds)

    mainline = subparsers.add_parser("sky130-mainline")
    mainline.add_argument("--sweep", default="config/sky130_candidate_sweep.yaml")
    mainline.add_argument("--pdk-root")
    mainline.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    mainline.add_argument("--split", choices=["train", "validation", "test"], default="train")
    mainline.add_argument("--max-rows", type=int, default=1)
    mainline.add_argument("--topology")
    mainline.add_argument("--source-dataset")
    mainline.add_argument("--output-root", default="outputs/sky130_mainline")
    mainline.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    mainline.add_argument("--param-space", default="examples/sample_params.yaml")
    mainline.add_argument("--max-candidates", type=int, default=10)
    mainline.add_argument("--seed", type=int, default=42)
    mainline.add_argument("--rounds", type=int, default=1)
    mainline.add_argument("--strategy", choices=["random", "adaptive", "genetic", "bayesian", "surrogate", "repair", "hybrid", "hybrid_goa", "physics_guided_hybrid"], default="adaptive")
    mainline.add_argument("--max-runs-per-round", type=int, default=3)
    mainline.add_argument("--patience", type=int, default=2)
    mainline.add_argument("--min-improvement", type=float, default=0.0)
    mainline.add_argument("--exploration-ratio", type=float, default=0.25)
    mainline.add_argument("--validation-config", default="config/sky130_validation.yaml")
    mainline.add_argument("--ngspice-cmd", default="ngspice")
    mainline.add_argument("--mock-dataset-json", default="examples/sky130_candidate_chain_row.json")
    mainline.add_argument("--mock-ngspice", action="store_true")
    mainline.add_argument("--require-real-ngspice", action="store_true")
    mainline.add_argument("--lightweight", action="store_true", default=True)
    mainline.add_argument("--full-validation", action="store_true")
    mainline.add_argument("--mock-if-unavailable", dest="mock_if_unavailable", action="store_true", default=True)
    mainline.add_argument("--no-mock-if-unavailable", dest="mock_if_unavailable", action="store_false")
    mainline.set_defaults(handler=handle_sky130_mainline)

    benchmark = subparsers.add_parser("strategy-benchmark")
    benchmark.add_argument("--sweep", default="config/sky130_candidate_sweep.yaml")
    benchmark.add_argument("--pdk-root")
    benchmark.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    benchmark.add_argument("--split", choices=["train", "validation", "test"], default="train")
    benchmark.add_argument("--max-rows", type=int, default=1)
    benchmark.add_argument("--topology")
    benchmark.add_argument("--source-dataset")
    benchmark.add_argument("--output-root", default="outputs/strategy_benchmark")
    benchmark.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    benchmark.add_argument("--param-space", default="examples/sample_params.yaml")
    benchmark.add_argument("--max-candidates", type=int, default=10)
    benchmark.add_argument("--seeds", default="42")
    benchmark.add_argument("--rounds", type=int, default=2)
    benchmark.add_argument("--max-runs-per-round", type=int, default=3)
    benchmark.add_argument("--validation-config", default="config/sky130_validation.yaml")
    benchmark.add_argument("--ngspice-cmd", default="ngspice")
    benchmark.add_argument("--mock-dataset-json", default="examples/sky130_candidate_chain_row.json")
    benchmark.add_argument("--mock-ngspice", action="store_true")
    benchmark.set_defaults(handler=handle_strategy_benchmark)


def handle_simulate_run(args: argparse.Namespace) -> int:
    if args.adapter == "csv-import":
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
    if args.adapter == "sky130-transient":
        try:
            run_sky130_transient(
                output_root=Path(args.output_dir),
                split=args.split,
                max_rows=args.max_rows,
                topology=args.topology or args.circuit_profile,
                source_dataset=args.source_dataset,
                dataset_name=args.dataset,
                mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
                mock_ngspice=args.mock_ngspice,
                ngspice_cmd=args.ngspice_cmd,
                spec_path=Path(args.spec),
                param_space_path=Path(args.param_space),
                max_candidates=args.max_candidates,
                seed=args.seed,
            )
        except Sky130DependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    print(f"unsupported simulate-run adapter: {args.adapter}", file=sys.stderr)
    return 2


def handle_simulate_sweep(args: argparse.Namespace) -> int:
    if args.adapter == "csv-import":
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
    if args.adapter == "sky130-sweep":
        try:
            run_sky130_sweep(
                sweep_path=Path(args.sweep),
                output_root=Path(args.output_root),
                pdk_root=Path(args.pdk_root) if args.pdk_root else None,
                split=args.split,
                max_rows=args.max_rows,
                topology=args.topology or args.circuit_profile,
                source_dataset=args.source_dataset,
                dataset_name=args.dataset,
                mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
                mock_ngspice=args.mock_ngspice,
                ngspice_cmd=args.ngspice_cmd,
                spec_path=Path(args.spec),
                param_space_path=Path(args.param_space),
                max_candidates=args.max_candidates,
                seed=args.seed,
                max_runs=args.max_runs,
            )
        except Sky130DependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    print(f"unsupported simulate-sweep adapter: {args.adapter}", file=sys.stderr)
    return 2


def handle_sky130_transient(args: argparse.Namespace) -> int:
    try:
        run_sky130_transient(
            output_root=Path(args.output_root),
            split=args.split,
            max_rows=args.max_rows,
            topology=args.topology,
            source_dataset=args.source_dataset,
            dataset_name=args.dataset,
            mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
            mock_ngspice=args.mock_ngspice,
            ngspice_cmd=args.ngspice_cmd,
            spec_path=Path(args.spec),
            param_space_path=Path(args.param_space),
            max_candidates=args.max_candidates,
            seed=args.seed,
            skip_netlist_structure=args.skip_netlist_structure,
        )
    except Sky130DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def handle_sky130_sweep(args: argparse.Namespace) -> int:
    try:
        run_sky130_sweep(
            sweep_path=Path(args.sweep),
            output_root=Path(args.output_root),
            pdk_root=Path(args.pdk_root) if args.pdk_root else None,
            split=args.split,
            max_rows=args.max_rows,
            topology=args.topology,
            source_dataset=args.source_dataset,
            dataset_name=args.dataset,
            mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
            mock_ngspice=args.mock_ngspice,
            ngspice_cmd=args.ngspice_cmd,
            spec_path=Path(args.spec),
            param_space_path=Path(args.param_space),
            max_candidates=args.max_candidates,
            seed=args.seed,
            max_runs=args.max_runs,
        )
    except Sky130DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def handle_optimize_rounds(args: argparse.Namespace) -> int:
    try:
        run_multi_round_optimization(
            sweep_path=Path(args.sweep),
            output_root=Path(args.output_root),
            rounds=args.rounds,
            max_runs_per_round=args.max_runs_per_round,
            patience=args.patience,
            min_improvement=args.min_improvement,
            exploration_ratio=args.exploration_ratio,
            pdk_root=Path(args.pdk_root) if args.pdk_root else None,
            split=args.split,
            max_rows=args.max_rows,
            topology=args.topology,
            source_dataset=args.source_dataset,
            dataset_name=args.dataset,
            mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
            mock_ngspice=args.mock_ngspice,
            ngspice_cmd=args.ngspice_cmd,
            spec_path=Path(args.spec),
            param_space_path=Path(args.param_space),
            max_candidates=args.max_candidates,
            seed=args.seed,
            strategy=args.strategy,
            validation_config_path=Path(args.validation_config) if args.validation_config else None,
        )
    except Sky130DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def handle_sky130_mainline(args: argparse.Namespace) -> int:
    try:
        run_sky130_mainline(
            sweep_path=Path(args.sweep),
            output_root=Path(args.output_root),
            validation_config_path=Path(args.validation_config) if args.validation_config else None,
            rounds=args.rounds,
            max_runs_per_round=args.max_runs_per_round,
            patience=args.patience,
            min_improvement=args.min_improvement,
            exploration_ratio=args.exploration_ratio,
            pdk_root=Path(args.pdk_root) if args.pdk_root else None,
            split=args.split,
            max_rows=args.max_rows,
            topology=args.topology,
            source_dataset=args.source_dataset,
            dataset_name=args.dataset,
            mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
            mock_ngspice=args.mock_ngspice,
            mock_if_unavailable=args.mock_if_unavailable,
            require_real_ngspice=args.require_real_ngspice,
            ngspice_cmd=args.ngspice_cmd,
            spec_path=Path(args.spec),
            param_space_path=Path(args.param_space),
            max_candidates=args.max_candidates,
            seed=args.seed,
            strategy=args.strategy,
            full_validation=args.full_validation,
        )
    except Sky130DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def handle_strategy_benchmark(args: argparse.Namespace) -> int:
    try:
        run_strategy_benchmark(
            sweep_path=Path(args.sweep),
            output_root=Path(args.output_root),
            validation_config_path=Path(args.validation_config) if args.validation_config else None,
            seeds=parse_seeds(args.seeds),
            rounds=args.rounds,
            max_runs_per_round=args.max_runs_per_round,
            pdk_root=Path(args.pdk_root) if args.pdk_root else None,
            split=args.split,
            max_rows=args.max_rows,
            topology=args.topology,
            source_dataset=args.source_dataset,
            dataset_name=args.dataset,
            mock_dataset_json=Path(args.mock_dataset_json) if args.mock_dataset_json else None,
            mock_ngspice=args.mock_ngspice,
            ngspice_cmd=args.ngspice_cmd,
            spec_path=Path(args.spec),
            param_space_path=Path(args.param_space),
            max_candidates=args.max_candidates,
        )
    except Sky130DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
