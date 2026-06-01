from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

import pandas as pd

from goa_eval.config import load_configs
from goa_eval.batch_eval import run_batch_evaluation
from goa_eval.ai_profile_assistant import run_ai_profile_assistant
from goa_eval.circuit_profiles import validate_profile_references
from goa_eval.csv_import_adapter import run_csv_import, run_csv_import_sweep
from goa_eval.demo_mainline import run_demo_mainline
from goa_eval.evaluation.feature_extractor import extract_waveform_features
from goa_eval.evaluation.mock_waveform import generate_mock_waveform
from goa_eval.evaluation.scoring import compute_metric_results
from goa_eval.goa_hybrid_optimizer import run_hybrid_goa_optimizer
from goa_eval.io_utils import copy_initial_raw_inputs, ensure_run_dirs, extract_archives, to_jsonable, write_json
from goa_eval.llm_analysis import run_llm_parameter_analysis
from goa_eval.multi_round_optimizer import run_multi_round_optimization
from goa_eval.optimizer import constrained_random_candidates, load_baseline_params, load_param_space, propose_candidates, write_candidate_outputs
from goa_eval.parameter_semantics import load_parameter_semantics
from goa_eval.parsers.design_parser import build_design_version, discover_design_roots
from goa_eval.parsers.mapping_parser import parse_mapping
from goa_eval.parsers.metric_table_parser import parse_metric_table
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.parsers.waveform_parser import read_waveform_csv
from goa_eval.product_demo.workflow import run_product_demo
from goa_eval.report.manifest import write_run_manifest
from goa_eval.report.markdown_report import write_markdown_report
from goa_eval.report.reporter import write_report_md
from goa_eval.report.summary_writer import write_metric_table, write_metrics_csv, write_summary_json
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown
from goa_eval.sky130_mainline import run_sky130_mainline
from goa_eval.sky130_sweep import run_sky130_sweep
from goa_eval.sky130_transient import Sky130DependencyError, run_sky130_transient
from goa_eval.strategy_benchmark import parse_seeds, run_strategy_benchmark
from goa_eval.goa_strategy_benchmark import DEFAULT_STRATEGIES as GOA_BENCH_STRATEGIES, run_goa_strategy_benchmark
from goa_eval.visualization.comparison_plotter import plot_v1_v8_comparison
from goa_eval.visualization.metric_plotter import plot_voh_bar
from goa_eval.visualization.version_compare_plotter import plot_timing_overview
from goa_eval.visualization.waveform_plotter import plot_waveform_overview


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "extract":
        extract_archives(Path(args.raw), _output_path(args))
        return 0
    if args.command == "parse":
        config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
        out = _output_path(args)
        ensure_run_dirs(out)
        designs = parse_designs(Path(args.input))
        write_design_summary(out, designs)
        write_netlist_parse_json(out, designs)
        specs = _parse_metric_table_if_available(Path(args.raw))
        if specs:
            write_metric_table(out, specs)
        return 0
    if args.command == "evaluate":
        config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
        out = _output_path(args)
        if args.design:
            out.mkdir(parents=True, exist_ok=True)
            design = parse_single_design(Path(args.design))
            comparison_designs = comparison_designs_for(design)
            return evaluate_designs_flat(out, [design], comparison_designs, config, thresholds, args.mock_waveform, out.name, args, design.root_dir)
        ensure_run_dirs(out)
        designs = parse_designs(Path(args.input))
        return evaluate_designs(out, designs, config, thresholds, args.mock_waveform, "dev_run", args, Path(args.input))
    if args.command == "all":
        root = Path.cwd()
        copy_initial_raw_inputs(root)
        raw = Path(args.raw)
        extracted = Path(args.input)
        extract_archives(raw, extracted)
        config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
        out = _output_path(args)
        ensure_run_dirs(out)
        designs = parse_designs(extracted)
        write_design_summary(out, designs)
        write_netlist_parse_json(out, designs)
        specs = _parse_metric_table_if_available(raw)
        if specs:
            write_metric_table(out, specs)
        return evaluate_designs(out, designs, config, thresholds, args.mock_waveform, out.name, args, extracted)
    if args.command == "evaluate-real":
        run_real_waveform_evaluation(
            waveform_path=Path(args.waveform),
            internal_waveform_path=Path(args.internal_waveform) if args.internal_waveform else None,
            output_dir=Path(args.output_dir),
            high_threshold=float(args.high_threshold) if args.high_threshold is not None else None,
            low_threshold=float(args.low_threshold) if args.low_threshold is not None else None,
            spec_path=Path(args.spec) if args.spec else None,
            stage_count=args.stage_count,
            output_node_pattern=args.output_node_pattern,
            stage_group_size=args.stage_group_size,
            topology=args.topology,
            circuit_profile=args.circuit_profile,
            profile_file=Path(args.profile_file) if args.profile_file else None,
        )
        return 0
    if args.command == "recommend":
        write_recommendations_markdown(
            summary_path=Path(args.summary),
            score_path=Path(args.score) if args.score else None,
            metrics_path=Path(args.metrics) if args.metrics else None,
            output_path=Path(args.output),
        )
        return 0
    if args.command == "product-demo":
        case_dir = run_product_demo(
            input_dir=Path(args.input_dir),
            output_dir=Path(args.output_dir),
            case_id=args.case_id,
        )
        print(f"Product demo package written to {case_dir}")
        return 0
    if args.command == "demo":
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
    if args.command == "evaluate-batch":
        run_batch_evaluation(runs_dir=Path(args.runs_dir), output_dir=Path(args.output_dir))
        return 0
    if args.command == "multi-agent-run":
        from goa_eval.multi_agent.availability import check_langgraph_availability

        availability = check_langgraph_availability()
        if not availability["available"]:
            print(availability["message"], file=sys.stderr)
            return 2
        from goa_eval.multi_agent.graph_app import run_multi_agent_task

        run_multi_agent_task(Path(args.task), Path(args.output_dir))
        return 0
    if args.command == "benchmark-run":
        from goa_eval.multi_agent.benchmark import run_benchmark_suite

        run_benchmark_suite(Path(args.suite), Path(args.output_dir))
        return 0
    if args.command == "propose-candidates":
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        score = json.loads(Path(args.score).read_text(encoding="utf-8")) if args.score else {}
        metrics = pd.read_csv(Path(args.metrics)) if args.metrics else pd.DataFrame()
        recommendations = build_recommendations(summary, score, metrics)
        param_space = load_param_space(Path(args.param_space))
        semantics = load_parameter_semantics(Path(args.params)) if args.params else None
        if args.strategy == "rule":
            candidates = propose_candidates(
                param_space,
                recommendations,
                profile_file=Path(args.profile_file) if args.profile_file else None,
                parameter_semantics=semantics,
            )
        else:
            candidates = constrained_random_candidates(
                param_space,
                recommendations,
                max_candidates=args.max_candidates,
                seed=args.seed,
                baseline_params=load_baseline_params(Path(args.baseline_params)) if args.baseline_params else None,
                profile_file=Path(args.profile_file) if args.profile_file else None,
                parameter_semantics=semantics,
            )
        write_candidate_outputs(candidates, csv_path=Path(args.output_csv), markdown_path=Path(args.output_md))
        return 0
    if args.command == "validate-config":
        validate_profile_references(
            profile_file=Path(args.profile_file),
            semantics_file=Path(args.params) if args.params else None,
        )
        print(f"validated {args.profile_file}" + (f" with {args.params}" if args.params else ""))
        return 0
    if args.command == "analyze-params":
        run_llm_parameter_analysis(
            summary_path=Path(args.summary),
            score_path=Path(args.score) if args.score else None,
            metrics_path=Path(args.metrics) if args.metrics else None,
            candidates_path=Path(args.candidates) if args.candidates else None,
            params_path=Path(args.params) if args.params else None,
            model=args.model,
            output_md=Path(args.output_md),
            output_json=Path(args.output_json),
            mock_response=args.mock_response,
        )
        return 0
    if args.command == "ai-profile-assistant":
        run_ai_profile_assistant(
            description_path=Path(args.description),
            output_dir=Path(args.output_dir),
            profile_file=Path(args.profile_file) if args.profile_file else None,
            params_file=Path(args.params) if args.params else None,
            metrics_file=Path(args.metrics) if args.metrics else None,
            score_file=Path(args.score) if args.score else None,
            model=args.model,
            mock_response=args.mock_response,
        )
        return 0
    if args.command == "csv-import":
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
    if args.command == "simulate-run":
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
    if args.command == "simulate-sweep":
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
    if args.command == "sky130-transient":
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
    if args.command == "sky130-sweep":
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
    if args.command == "optimize-rounds":
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
    if args.command == "sky130-mainline":
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
    if args.command == "strategy-benchmark":
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
    if args.command == "hybrid-goa-optimize":
        run_hybrid_goa_optimizer(
            history_path=Path(args.history) if args.history else None,
            leaderboard_path=Path(args.leaderboard) if args.leaderboard else None,
            param_space_path=Path(args.param_space) if args.param_space else None,
            output_root=Path(args.output_root),
            max_candidates=args.max_candidates,
            seed=args.seed,
        )
        return 0
    if args.command == "goa-strategy-benchmark":
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
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goa-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["extract", "parse", "evaluate", "all"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--raw", default="data/raw")
        cmd.add_argument("--input", default="data/extracted")
        cmd.add_argument("--design")
        cmd.add_argument("--out")
        cmd.add_argument("--config", default="configs/default.yaml")
        cmd.add_argument("--thresholds", default="configs/thresholds.yaml")
        cmd.add_argument("--mock-waveform", action="store_true")
        cmd.add_argument("--waveform-csv")
        cmd.add_argument("--waveform-dir")
        cmd.add_argument("--strict", action="store_true")
    real = sub.add_parser("evaluate-real")
    real.add_argument("--waveform", required=True)
    real.add_argument("--internal-waveform")
    real.add_argument("--output-dir", default="outputs")
    real.add_argument("--spec", default="config/spec.yaml")
    real.add_argument("--high-threshold", type=float)
    real.add_argument("--low-threshold", type=float)
    real.add_argument("--stage-count", type=int)
    real.add_argument("--output-node-pattern")
    real.add_argument("--stage-group-size", type=int)
    real.add_argument("--topology")
    real.add_argument("--circuit-profile")
    real.add_argument("--profile-file")
    recommend = sub.add_parser("recommend")
    recommend.add_argument("--summary", required=True)
    recommend.add_argument("--score")
    recommend.add_argument("--metrics")
    recommend.add_argument("--output", default="outputs/recommendations.md")
    product_demo = sub.add_parser("product-demo")
    product_demo.add_argument("--input-dir", required=True)
    product_demo.add_argument("--output-dir", default="outputs/product_demo")
    product_demo.add_argument("--case-id", required=True)
    demo = sub.add_parser("demo")
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
    batch = sub.add_parser("evaluate-batch")
    batch.add_argument("--runs-dir", required=True)
    batch.add_argument("--output-dir", default="outputs_batch")
    multi_agent = sub.add_parser("multi-agent-run")
    multi_agent.add_argument("--task", required=True)
    multi_agent.add_argument("--output-dir", required=True)
    benchmark = sub.add_parser("benchmark-run")
    benchmark.add_argument("--suite", required=True)
    benchmark.add_argument("--output-dir", required=True)
    candidates = sub.add_parser("propose-candidates")
    candidates.add_argument("--summary", required=True)
    candidates.add_argument("--score")
    candidates.add_argument("--metrics")
    candidates.add_argument("--param-space", required=True)
    candidates.add_argument("--strategy", choices=["constrained-random", "rule"], default="constrained-random")
    candidates.add_argument("--max-candidates", type=int, default=10)
    candidates.add_argument("--seed", type=int, default=42)
    candidates.add_argument("--baseline-params")
    candidates.add_argument("--profile-file")
    candidates.add_argument("--params")
    candidates.add_argument("--output-csv", default="outputs/next_candidates.csv")
    candidates.add_argument("--output-md", default="outputs/next_candidates.md")
    validate = sub.add_parser("validate-config")
    validate.add_argument("--profile-file", required=True)
    validate.add_argument("--params")
    analyze = sub.add_parser("analyze-params")
    analyze.add_argument("--summary", required=True)
    analyze.add_argument("--score")
    analyze.add_argument("--metrics")
    analyze.add_argument("--candidates")
    analyze.add_argument("--params")
    analyze.add_argument("--model", default="deepseek-v4-pro")
    analyze.add_argument("--mock-response")
    analyze.add_argument("--output-md", default="outputs/llm_parameter_analysis.md")
    analyze.add_argument("--output-json", default="outputs/llm_parameter_analysis.json")
    assistant = sub.add_parser("ai-profile-assistant")
    assistant.add_argument("--description", required=True)
    assistant.add_argument("--profile-file")
    assistant.add_argument("--params")
    assistant.add_argument("--metrics")
    assistant.add_argument("--score")
    assistant.add_argument("--model", default="deepseek-v4-pro")
    assistant.add_argument("--mock-response")
    assistant.add_argument("--output-dir", default="outputs/ai_profile_assistant")
    csv_import = sub.add_parser("csv-import")
    _add_csv_import_args(csv_import)
    simulate_run = sub.add_parser("simulate-run")
    simulate_run.add_argument("--adapter", choices=["csv-import", "sky130-transient"], required=True)
    _add_csv_import_args(simulate_run)
    _add_sky130_common_args(simulate_run, output_arg=None)
    simulate_sweep = sub.add_parser("simulate-sweep")
    simulate_sweep.add_argument("--adapter", choices=["csv-import", "sky130-sweep"], required=True)
    simulate_sweep.add_argument("--input-root", default="outputs/csv_import_inputs")
    simulate_sweep.add_argument("--output-root", default="outputs/simulate_sweep")
    simulate_sweep.add_argument("--sweep", default="config/sky130_sweep.yaml")
    simulate_sweep.add_argument("--pdk-root")
    simulate_sweep.add_argument("--max-runs", type=int)
    _add_common_profile_args(simulate_sweep)
    _add_sky130_common_args(simulate_sweep, output_arg=None)
    sky130 = sub.add_parser("sky130-transient")
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
    sweep = sub.add_parser("sky130-sweep")
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
    optimize = sub.add_parser("optimize-rounds")
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
    mainline = sub.add_parser("sky130-mainline")
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
    benchmark_strategies = sub.add_parser("strategy-benchmark")
    benchmark_strategies.add_argument("--sweep", default="config/sky130_candidate_sweep.yaml")
    benchmark_strategies.add_argument("--pdk-root")
    benchmark_strategies.add_argument("--dataset", default="pphilip/analog-circuits-sky130")
    benchmark_strategies.add_argument("--split", choices=["train", "validation", "test"], default="train")
    benchmark_strategies.add_argument("--max-rows", type=int, default=1)
    benchmark_strategies.add_argument("--topology")
    benchmark_strategies.add_argument("--source-dataset")
    benchmark_strategies.add_argument("--output-root", default="outputs/strategy_benchmark")
    benchmark_strategies.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    benchmark_strategies.add_argument("--param-space", default="examples/sample_params.yaml")
    benchmark_strategies.add_argument("--max-candidates", type=int, default=10)
    benchmark_strategies.add_argument("--seeds", default="42")
    benchmark_strategies.add_argument("--rounds", type=int, default=2)
    benchmark_strategies.add_argument("--max-runs-per-round", type=int, default=3)
    benchmark_strategies.add_argument("--validation-config", default="config/sky130_validation.yaml")
    benchmark_strategies.add_argument("--ngspice-cmd", default="ngspice")
    benchmark_strategies.add_argument("--mock-dataset-json", default="examples/sky130_candidate_chain_row.json")
    benchmark_strategies.add_argument("--mock-ngspice", action="store_true")
    hybrid = sub.add_parser("hybrid-goa-optimize")
    hybrid.add_argument("--history")
    hybrid.add_argument("--leaderboard")
    hybrid.add_argument("--param-space", default="examples/sample_params.yaml")
    hybrid.add_argument("--output-root", default="outputs/hybrid_goa")
    hybrid.add_argument("--max-candidates", type=int, default=30)
    hybrid.add_argument("--seed", type=int, default=42)
    goa_bench = sub.add_parser("goa-strategy-benchmark")
    goa_bench.add_argument("--history")
    goa_bench.add_argument("--leaderboard")
    goa_bench.add_argument("--param-space", default="examples/sample_params.yaml")
    goa_bench.add_argument("--output-root", default="outputs/goa_strategy_benchmark")
    goa_bench.add_argument("--strategies", default=",".join(GOA_BENCH_STRATEGIES))
    goa_bench.add_argument("--max-candidates", type=int, default=30)
    goa_bench.add_argument("--seeds", default="1,2,3")
    goa_bench.add_argument("--top-k", type=int, default=10)
    return parser


def _add_common_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default="config/sky130_transient_spec.yaml")
    parser.add_argument("--param-space", default="examples/sample_params.yaml")
    parser.add_argument("--circuit-profile")
    parser.add_argument("--profile-file")
    parser.add_argument("--params")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)


def _add_csv_import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-dir", default=".")
    parser.add_argument("--output-dir", default="outputs/csv_import")
    _add_common_profile_args(parser)


def _add_sky130_common_args(parser: argparse.ArgumentParser, *, output_arg: str | None) -> None:
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


def _output_path(args) -> Path:
    if args.out:
        return Path(args.out)
    if args.command == "evaluate" and args.design:
        return Path("outputs")
    return Path("outputs/dev_run")


def parse_designs(extracted_dir: Path):
    designs = []
    for root in discover_design_roots(extracted_dir):
        netlist = next(iter(sorted(root.glob("*.netlist"))), None)
        mapping_path = _first_mapping_path(root)
        if netlist is None:
            continue
        parsed = parse_netlist(netlist)
        mapping = parse_mapping(mapping_path) if mapping_path else None
        designs.append(build_design_version(_infer_design_name(root, netlist), root, parsed, mapping))
    return designs


def parse_single_design(design_dir: Path):
    root = _resolve_design_dir(design_dir)
    netlist = next(iter(sorted(root.glob("*.netlist"))), None)
    mapping_path = _first_mapping_path(root)
    if netlist is None:
        raise SystemExit(f"No .netlist file found in {root}")
    parsed = parse_netlist(netlist)
    mapping = parse_mapping(mapping_path) if mapping_path else None
    return build_design_version(_infer_design_name(root, netlist), root, parsed, mapping)


def _first_mapping_path(root: Path) -> Path | None:
    matches = sorted([*root.glob("*.mapping"), *root.glob("*.map")])
    return matches[0] if matches else None


def _infer_design_name(root: Path, netlist: Path) -> str:
    if root.name.startswith("v"):
        return root.name
    match = re.search(r"\bv(\d+)\b|_v(\d+)(?:_|$)", netlist.stem, flags=re.IGNORECASE)
    if match:
        return f"v{match.group(1) or match.group(2)}"
    return root.name


def comparison_designs_for(target):
    designs = {target.name: target}
    parent = target.root_dir.parent
    for name in ["v1", "v8"]:
        root = parent / name
        if name not in designs and root.exists():
            designs[name] = parse_single_design(root)
    return [designs[name] for name in sorted(designs)]


def _resolve_design_dir(design_dir: Path) -> Path:
    if design_dir.exists():
        return design_dir
    parts = design_dir.parts
    if len(parts) >= 3 and parts[-3:-1] == ("data", "designs"):
        extracted = Path(*parts[:-2]) / "extracted" / parts[-1]
        if extracted.exists():
            return extracted
    raise SystemExit(f"Design directory not found: {design_dir}")


def evaluate_designs(out: Path, designs, config: dict, thresholds: dict, mock_waveform: bool, run_id: str, args, input_design_path: Path) -> int:
    target = next((design for design in designs if design.name == "v8"), designs[-1] if designs else None)
    if target is None:
        raise SystemExit("No design versions found")

    waveform = _load_waveform(target.name, thresholds, mock_waveform, args.waveform_csv)
    features = extract_waveform_features(waveform, thresholds)
    results = compute_metric_results(target, features, waveform.data_source, waveform.engineering_validity, thresholds)

    write_metrics_csv(out / "metrics" / "metrics.csv", run_id, results)
    summary = write_summary_json(out, run_id, waveform.data_source, waveform.engineering_validity, [design.name for design in designs], results)
    write_markdown_report(out / "reports" / "summary.md", summary)
    comparison_path = out / "figures" / "v1_v8_comparison.png"
    plot_v1_v8_comparison(designs, summary, thresholds, comparison_path)
    write_report_md(
        out / "report.md",
        summary=summary,
        input_design_path=input_design_path,
        metrics_path=Path("metrics") / "metrics.csv",
        manifest_path=Path("run_manifest.json"),
        figure_path=Path("figures") / comparison_path.name,
    )
    write_run_manifest(
        out / "run_manifest.json",
        run_id=run_id,
        input_design_path=input_design_path,
        config=config,
        thresholds=thresholds,
        data_source=waveform.data_source,
        engineering_validity=waveform.engineering_validity,
    )
    plot_waveform_overview(waveform, out / "figures" / "waveform_v8_mock.png")
    plot_voh_bar(features, out / "figures" / "voh_bar.png", waveform.data_source, waveform.engineering_validity)
    plot_timing_overview(features, out / "figures" / "timing_overview.png", waveform.data_source, waveform.engineering_validity)
    (out / "logs" / "run.log").write_text("run completed with mock waveform\n", encoding="utf-8")
    return 0


def evaluate_designs_flat(out: Path, designs, comparison_designs, config: dict, thresholds: dict, mock_waveform: bool, run_id: str, args, input_design_path: Path) -> int:
    target = designs[0] if designs else None
    if target is None:
        raise SystemExit("No design version found")

    waveform = _load_waveform(target.name, thresholds, mock_waveform, args.waveform_csv)
    features = extract_waveform_features(waveform, thresholds)
    results = compute_metric_results(target, features, waveform.data_source, waveform.engineering_validity, thresholds)

    write_metrics_csv(out / "metrics.csv", run_id, results)
    summary = write_summary_json(out, run_id, waveform.data_source, waveform.engineering_validity, [design.name for design in designs], results)
    comparison_path = out / "figures" / "v1_v8_comparison.png"
    plot_v1_v8_comparison(comparison_designs, summary, thresholds, comparison_path)
    write_report_md(
        out / "report.md",
        summary=summary,
        input_design_path=input_design_path,
        metrics_path=Path("metrics.csv"),
        manifest_path=Path("run_manifest.json"),
        figure_path=Path("figures") / comparison_path.name,
    )
    write_run_manifest(
        out / "run_manifest.json",
        run_id=run_id,
        input_design_path=input_design_path,
        config=config,
        thresholds=thresholds,
        data_source=waveform.data_source,
        engineering_validity=waveform.engineering_validity,
    )
    return 0


def _load_waveform(version_name: str, thresholds: dict, mock_waveform: bool, waveform_csv: str | None):
    if waveform_csv:
        return read_waveform_csv(Path(waveform_csv), version_name)
    if not mock_waveform:
        raise SystemExit("--mock-waveform or --waveform-csv is required")
    return generate_mock_waveform(version_name, thresholds)


def write_design_summary(out: Path, designs) -> None:
    rows = []
    for design in designs:
        mos = [device for device in design.devices if device.kind == "mos"]
        caps = [device for device in design.devices if device.kind == "capacitor"]
        rows.append(
            {
                "name": design.name,
                "root_dir": str(design.root_dir),
                "netlist_path": str(design.netlist_path) if design.netlist_path else None,
                "mapping_path": str(design.mapping_path) if design.mapping_path else None,
                "design_path": str(design.design_path) if design.design_path else None,
                "image_path": str(design.image_path) if design.image_path else None,
                "device_count": len(design.devices),
                "mos_count": len(mos),
                "capacitor_count": len(caps),
                "subckt_count": len(design.subckts),
                "cascade_chain": design.cascade_chain,
                "mapping_record_count": len(design.mapping.records) if design.mapping else 0,
                "W_sum": sum(device.params_si.get("W", 0.0) for device in mos),
                "C_sum": sum(device.params_si.get("C", 0.0) for device in caps),
                "warnings": design.warnings,
            }
        )
    write_json(out / "metrics" / "design_summary.json", rows)


def write_netlist_parse_json(out: Path, designs) -> None:
    rows = []
    for design in designs:
        rows.append(
            {
                "name": design.name,
                "root_dir": str(design.root_dir),
                "netlist_path": str(design.netlist_path) if design.netlist_path else None,
                "devices": to_jsonable(design.devices),
                "subckts": to_jsonable(design.subckts),
                "cascade_chain": design.cascade_chain,
                "warnings": design.warnings,
            }
        )
    write_json(out / "metrics" / "netlist_parse.json", rows)


def _parse_metric_table_if_available(raw_dir: Path):
    metric_path = _metric_table_path(raw_dir)
    if metric_path is None:
        return []
    return parse_metric_table(metric_path)


def _metric_table_path(raw_dir: Path) -> Path | None:
    preferred = raw_dir / "评价指标表.html"
    if preferred.exists():
        return preferred
    matches = list(raw_dir.glob("*.html"))
    return matches[0] if matches else None


if __name__ == "__main__":
    raise SystemExit(main())
