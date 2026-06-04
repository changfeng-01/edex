from __future__ import annotations

import argparse
import sys
from pathlib import Path

from goa_eval.demo_mainline import run_demo_mainline
from goa_eval.goa_hybrid_optimizer import run_hybrid_goa_optimizer
from goa_eval.goa_strategy_benchmark import DEFAULT_STRATEGIES as GOA_BENCH_STRATEGIES, run_goa_strategy_benchmark
from goa_eval.product_demo.workflow import run_product_demo


def register(subparsers: argparse._SubParsersAction) -> None:
    product_demo = subparsers.add_parser("product-demo")
    product_demo.add_argument("--input-dir", required=True)
    product_demo.add_argument("--output-dir", default="outputs/product_demo")
    product_demo.add_argument("--case-id", required=True)
    product_demo.set_defaults(handler=handle_product_demo)

    demo = subparsers.add_parser("demo")
    demo.add_argument("--case-id", default="public_demo")
    demo.add_argument("--waveform", default="examples/sample_waveform.csv")
    demo.add_argument("--param-space", default="examples/sample_params.yaml")
    demo.add_argument("--spec", default="config/spec.yaml")
    demo.add_argument("--demo-run-dir")
    demo.add_argument("--output-root", default="outputs/product_demo")
    demo.add_argument("--frontend-data-root", default="frontend/public/demo_data")
    demo.add_argument("--max-candidates", type=int, default=10)
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--mock-response", default=None)
    demo.set_defaults(handler=handle_demo)

    multi_agent = subparsers.add_parser("multi-agent-run")
    multi_agent.add_argument("--task", required=True)
    multi_agent.add_argument("--output-dir", required=True)
    multi_agent.set_defaults(handler=handle_multi_agent_run)

    benchmark = subparsers.add_parser("benchmark-run")
    benchmark.add_argument("--suite", required=True)
    benchmark.add_argument("--output-dir", required=True)
    benchmark.set_defaults(handler=handle_benchmark_run)

    hybrid = subparsers.add_parser("hybrid-goa-optimize")
    hybrid.add_argument("--history")
    hybrid.add_argument("--leaderboard")
    hybrid.add_argument("--param-space", default="examples/sample_params.yaml")
    hybrid.add_argument("--output-root", default="outputs/hybrid_goa")
    hybrid.add_argument("--max-candidates", type=int, default=30)
    hybrid.add_argument("--seed", type=int, default=42)
    hybrid.set_defaults(handler=handle_hybrid_goa_optimize)

    goa_bench = subparsers.add_parser("goa-strategy-benchmark")
    goa_bench.add_argument("--history")
    goa_bench.add_argument("--leaderboard")
    goa_bench.add_argument("--param-space", default="examples/sample_params.yaml")
    goa_bench.add_argument("--output-root", default="outputs/goa_strategy_benchmark")
    goa_bench.add_argument("--strategies", default=",".join(GOA_BENCH_STRATEGIES))
    goa_bench.add_argument("--max-candidates", type=int, default=30)
    goa_bench.add_argument("--seeds", default="1,2,3")
    goa_bench.add_argument("--top-k", type=int, default=10)
    goa_bench.set_defaults(handler=handle_goa_strategy_benchmark)


def handle_product_demo(args: argparse.Namespace) -> int:
    case_dir = run_product_demo(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        case_id=args.case_id,
    )
    print(f"Product demo package written to {case_dir}")
    return 0


def handle_demo(args: argparse.Namespace) -> int:
    manifest = run_demo_mainline(
        case_id=args.case_id,
        waveform_path=Path(args.waveform),
        param_space_path=Path(args.param_space),
        demo_run_dir=Path(args.demo_run_dir) if args.demo_run_dir else None,
        product_demo_root=Path(args.output_root),
        frontend_data_root=Path(args.frontend_data_root),
        spec_path=Path(args.spec),
        seed=args.seed,
        max_candidates=args.max_candidates,
        mock_response=args.mock_response,
    )
    print(f"CircuitPilot demo package written to {manifest['output_directories']['product_demo_case_dir']}")
    print(f"Dashboard data synced to {manifest['output_directories']['frontend_demo_data_dir']}")
    return 0


def handle_multi_agent_run(args: argparse.Namespace) -> int:
    from goa_eval.multi_agent.availability import check_langgraph_availability

    availability = check_langgraph_availability()
    if not availability["available"]:
        print(availability["message"], file=sys.stderr)
        return 2
    from goa_eval.multi_agent.graph_app import run_multi_agent_task

    run_multi_agent_task(Path(args.task), Path(args.output_dir))
    return 0


def handle_benchmark_run(args: argparse.Namespace) -> int:
    from goa_eval.multi_agent.benchmark import run_benchmark_suite

    run_benchmark_suite(Path(args.suite), Path(args.output_dir))
    return 0


def handle_hybrid_goa_optimize(args: argparse.Namespace) -> int:
    run_hybrid_goa_optimizer(
        history_path=Path(args.history) if args.history else None,
        leaderboard_path=Path(args.leaderboard) if args.leaderboard else None,
        param_space_path=Path(args.param_space) if args.param_space else None,
        output_root=Path(args.output_root),
        max_candidates=args.max_candidates,
        seed=args.seed,
    )
    return 0


def handle_goa_strategy_benchmark(args: argparse.Namespace) -> int:
    run_goa_strategy_benchmark(
        history_path=Path(args.history) if args.history else None,
        leaderboard_path=Path(args.leaderboard) if args.leaderboard else None,
        param_space_path=Path(args.param_space),
        output_root=Path(args.output_root),
        strategies=args.strategies.split(",") if args.strategies else None,
        max_candidates=args.max_candidates,
        seeds=[int(item.strip()) for item in args.seeds.split(",") if item.strip()],
        top_k=args.top_k,
    )
    return 0
