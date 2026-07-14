from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from goa_eval.ai_profile_assistant import run_ai_profile_assistant
from goa_eval.batch_eval import run_batch_evaluation
from goa_eval.circuit_profiles import validate_profile_references
from goa_eval.cli_commands.common import add_csv_import_args, add_empyrean_import_args
from goa_eval.csv_import_adapter import run_csv_import
from goa_eval.empyrean.case_importer import run_empyrean_import
from goa_eval.llm_analysis import run_llm_parameter_analysis
from goa_eval.optimizer import constrained_random_candidates, load_baseline_params, load_param_space, propose_candidates, write_candidate_outputs
from goa_eval.parameter_semantics import load_parameter_semantics
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown
from goa_eval.waveform_diagnostic_training import train_waveform_diagnostic_model


def register(subparsers: argparse._SubParsersAction) -> None:
    register_real_evaluation_commands(subparsers)
    register_candidate_analysis_commands(subparsers)
    register_import_commands(subparsers)


def register_real_evaluation_commands(subparsers: argparse._SubParsersAction) -> None:
    real = subparsers.add_parser("evaluate-real")
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
    real.set_defaults(handler=handle_evaluate_real)

    diagnostic = subparsers.add_parser("train-waveform-diagnostic")
    diagnostic.add_argument("--waveform", required=True)
    diagnostic.add_argument("--nominal-sp")
    diagnostic.add_argument("--netlist")
    diagnostic.add_argument("--model-card", action="append", default=[])
    diagnostic.add_argument("--spec", default="config/spec.yaml")
    diagnostic.add_argument("--output-dir", default="outputs/waveform_diagnostic")
    diagnostic.add_argument("--random-state", type=int, default=42)
    diagnostic.set_defaults(handler=handle_train_waveform_diagnostic)

    recommend = subparsers.add_parser("recommend")
    recommend.add_argument("--summary", required=True)
    recommend.add_argument("--score")
    recommend.add_argument("--metrics")
    recommend.add_argument("--output", default="outputs/recommendations.md")
    recommend.set_defaults(handler=handle_recommend)

    batch = subparsers.add_parser("evaluate-batch")
    batch.add_argument("--runs-dir", required=True)
    batch.add_argument("--output-dir", default="outputs_batch")
    batch.set_defaults(handler=handle_evaluate_batch)


def register_candidate_analysis_commands(subparsers: argparse._SubParsersAction) -> None:
    candidates = subparsers.add_parser("propose-candidates")
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
    candidates.set_defaults(handler=handle_propose_candidates)

    validate = subparsers.add_parser("validate-config")
    validate.add_argument("--profile-file", required=True)
    validate.add_argument("--params")
    validate.set_defaults(handler=handle_validate_config)

    analyze = subparsers.add_parser("analyze-params")
    analyze.add_argument("--summary", required=True)
    analyze.add_argument("--score")
    analyze.add_argument("--metrics")
    analyze.add_argument("--candidates")
    analyze.add_argument("--params")
    analyze.add_argument("--model", default="deepseek-v4-pro")
    analyze.add_argument("--mock-response")
    analyze.add_argument("--output-md", default="outputs/llm_parameter_analysis.md")
    analyze.add_argument("--output-json", default="outputs/llm_parameter_analysis.json")
    analyze.set_defaults(handler=handle_analyze_params)

    assistant = subparsers.add_parser("ai-profile-assistant")
    assistant.add_argument("--description", required=True)
    assistant.add_argument("--profile-file")
    assistant.add_argument("--params")
    assistant.add_argument("--metrics")
    assistant.add_argument("--score")
    assistant.add_argument("--model", default="deepseek-v4-pro")
    assistant.add_argument("--mock-response")
    assistant.add_argument("--output-dir", default="outputs/ai_profile_assistant")
    assistant.set_defaults(handler=handle_ai_profile_assistant)


def register_import_commands(subparsers: argparse._SubParsersAction) -> None:
    csv_import = subparsers.add_parser("csv-import")
    add_csv_import_args(csv_import)
    csv_import.set_defaults(handler=handle_csv_import)

    empyrean_import = subparsers.add_parser("empyrean-import")
    empyrean_import.add_argument("--input-dir", default="examples/empyrean_case")
    empyrean_import.add_argument("--output-dir", default="outputs/empyrean_case")
    empyrean_import.add_argument("--case-id", required=True)
    empyrean_import.add_argument("--generate-candidates", action="store_true")
    empyrean_import.add_argument("--stage-count", type=int)
    empyrean_import.add_argument("--output-node-pattern")
    empyrean_import.add_argument("--topology")
    add_empyrean_import_args(empyrean_import)
    empyrean_import.set_defaults(handler=handle_empyrean_import)


def handle_evaluate_real(args: argparse.Namespace) -> int:
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


def handle_train_waveform_diagnostic(args: argparse.Namespace) -> int:
    artifacts = train_waveform_diagnostic_model(
        waveform_path=Path(args.waveform),
        nominal_sp=Path(args.nominal_sp) if args.nominal_sp else None,
        netlist=Path(args.netlist) if args.netlist else None,
        model_cards=[Path(path) for path in args.model_card],
        spec_path=Path(args.spec) if args.spec else None,
        output_dir=Path(args.output_dir),
        random_state=args.random_state,
    )
    print(artifacts.report.get("status"))
    print(Path(args.output_dir) / "diagnostic_model_report.json")
    return 0


def handle_recommend(args: argparse.Namespace) -> int:
    write_recommendations_markdown(
        summary_path=Path(args.summary),
        score_path=Path(args.score) if args.score else None,
        metrics_path=Path(args.metrics) if args.metrics else None,
        output_path=Path(args.output),
    )
    return 0


def handle_evaluate_batch(args: argparse.Namespace) -> int:
    run_batch_evaluation(runs_dir=Path(args.runs_dir), output_dir=Path(args.output_dir))
    return 0


def handle_propose_candidates(args: argparse.Namespace) -> int:
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


def handle_validate_config(args: argparse.Namespace) -> int:
    validate_profile_references(
        profile_file=Path(args.profile_file),
        semantics_file=Path(args.params) if args.params else None,
    )
    print(f"validated {args.profile_file}" + (f" with {args.params}" if args.params else ""))
    return 0


def handle_analyze_params(args: argparse.Namespace) -> int:
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


def handle_ai_profile_assistant(args: argparse.Namespace) -> int:
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


def handle_csv_import(args: argparse.Namespace) -> int:
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


def handle_empyrean_import(args: argparse.Namespace) -> int:
    run_empyrean_import(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        case_id=args.case_id,
        spec_path=Path(args.spec),
        param_space_path=Path(args.param_space),
        generate_candidates=args.generate_candidates,
        stage_count=args.stage_count,
        output_node_pattern=args.output_node_pattern,
        topology=args.topology,
        circuit_profile=args.circuit_profile,
        profile_file=Path(args.profile_file) if args.profile_file else None,
        params_file=Path(args.params) if args.params else None,
        max_candidates=args.max_candidates,
        seed=args.seed,
    )
    return 0
