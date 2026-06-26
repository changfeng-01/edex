from __future__ import annotations

import argparse
from pathlib import Path

from goa_eval.pia_ca_llso.benchmark import run_ablation_benchmark
from goa_eval.pia_ca_llso.integration import CandidateAdapter, HistoryAdapter
from goa_eval.pia_ca_llso.io import ensure_output_dir, read_config, write_json, write_markdown
from goa_eval.pia_ca_llso.labeling import assign_level_labels, summarize_label_distribution
from goa_eval.pia_ca_llso.loop import suggest_next_run
from goa_eval.pia_ca_llso.report import render_candidate_report
from goa_eval.pia_ca_llso.training_data import build_training_data_from_db


def register(subparsers: argparse._SubParsersAction) -> None:
    label = subparsers.add_parser("pia-label")
    label.add_argument("--history-csv", required=True)
    label.add_argument("--config")
    label.add_argument("--output-dir", required=True)
    label.add_argument("--score-col", default="overall_score")
    label.add_argument("--hard-pass-col", default="hard_constraint_passed")
    label.set_defaults(handler=handle_pia_label)

    suggest = subparsers.add_parser("pia-suggest")
    suggest.add_argument("--history-csv", required=True)
    suggest.add_argument("--candidate-csv", required=True)
    suggest.add_argument("--config")
    suggest.add_argument("--output-dir", required=True)
    suggest.add_argument("--strategy", default="pia_physics_distance")
    suggest.add_argument("--top-k", type=int, default=4)
    suggest.add_argument("--seed", type=int, default=42)
    suggest.set_defaults(handler=handle_pia_suggest)

    benchmark = subparsers.add_parser("pia-benchmark")
    benchmark.add_argument("--history-csv", required=True)
    benchmark.add_argument("--candidate-csv", required=True)
    benchmark.add_argument("--config")
    benchmark.add_argument("--output-dir", required=True)
    benchmark.add_argument("--strategies", default="random,ca_llso_raw_distance,pia_physics_distance,pia_capm_distance,adaptive_pia_capm,classifier_level_hybrid")
    benchmark.add_argument("--target-score", type=float, default=80)
    benchmark.add_argument("--seed", type=int, default=42)
    benchmark.set_defaults(handler=handle_pia_benchmark)

    contract = subparsers.add_parser("pia-export-contract")
    contract.add_argument("--output-dir", required=True)
    contract.set_defaults(handler=handle_pia_export_contract)

    train = subparsers.add_parser("pia-train-from-db")
    train.add_argument("--paper-db", type=Path, default=Path("data/paper_database"))
    train.add_argument("--history-root", type=Path, default=Path("outputs"))
    train.add_argument("--config", type=Path, default=Path("config/pia_ca_llso_goa_profile.yaml"))
    train.add_argument("--output-dir", type=Path, default=Path("outputs/pia_training_from_db"))
    train.add_argument("--optimization-dataset", type=Path, action="append", default=[])
    train.add_argument("--candidate-csv", type=Path)
    train.set_defaults(handler=handle_pia_train_from_db)


def handle_pia_label(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    history = HistoryAdapter().load(args.history_csv)
    labeled = assign_level_labels(history, score_col=args.score_col, hard_pass_col=args.hard_pass_col)
    labeled.to_csv(output_dir / "labeled_history.csv", index=False)
    summary = summarize_label_distribution(labeled)
    summary.update({"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"})
    write_json(output_dir / "label_summary.json", summary)
    write_markdown(
        output_dir / "label_report.md",
        "# PIA-CA-LLSO Label Report\n\n"
        "Labels are derived from externally evaluated simulation CSV rows.\n\n"
        "- data_source = real_simulation_csv\n"
        "- engineering_validity = simulation_only\n\n"
        f"{summary}\n",
    )
    return 0


def handle_pia_suggest(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    config = read_config(args.config)
    history = HistoryAdapter().load(args.history_csv)
    candidates = CandidateAdapter().load(args.candidate_csv)
    result = suggest_next_run(history, candidates, config, strategy=args.strategy, top_k=args.top_k)
    result.selected_candidates.to_csv(output_dir / "pia_selected_candidates.csv", index=False)
    write_json(output_dir / "pia_candidate_explanations.json", result.explanation_report)
    write_json(output_dir / "pia_feature_report.json", result.feature_report)
    write_json(output_dir / "pia_model_report.json", result.model_report)
    write_markdown(output_dir / "pia_candidate_report.md", render_candidate_report(result.selected_candidates, result.model_report))
    return 0


def handle_pia_benchmark(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    config = read_config(args.config)
    history = HistoryAdapter().load(args.history_csv)
    candidates = CandidateAdapter().load(args.candidate_csv)
    strategies = [strategy.strip() for strategy in args.strategies.split(",") if strategy.strip()]
    run_ablation_benchmark(history, candidates, output_dir, strategies=strategies, target_score=args.target_score, config=config)
    return 0


def handle_pia_export_contract(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    write_markdown(
        output_dir / "pia_api_contract.md",
        "# PIA-CA-LLSO API Contract\n\n"
        "PIA consumes history/candidate CSV files and emits next-run simulation suggestions.\n\n"
        "- data_source = real_simulation_csv\n"
        "- engineering_validity = simulation_only\n",
    )
    write_json(output_dir / "pia_history_schema.json", {"required": ["sample_id", "overall_score", "hard_constraint_passed"]})
    write_json(output_dir / "pia_candidate_schema.json", {"required": ["candidate_id"], "recommended": ["parameter columns"]})
    write_json(output_dir / "pia_output_schema.json", {"required": ["candidate_id", "selected_rank", "candidate_role"]})
    return 0


def handle_pia_train_from_db(args: argparse.Namespace) -> int:
    artifacts = build_training_data_from_db(
        paper_db=args.paper_db,
        history_root=args.history_root,
        output_dir=args.output_dir,
        config_path=args.config,
        optimization_datasets=args.optimization_dataset,
        candidate_csv=args.candidate_csv,
    )
    print(artifacts.train_report.get("status"))
    print(args.output_dir / "pia_training_history.csv")
    return 0
