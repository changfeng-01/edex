from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from goa_eval.pia_ca_llso.benchmark import run_ablation_benchmark, run_closed_loop_benchmark
from goa_eval.pia_ca_llso.boundary_audit import audit_evolution_outputs
from goa_eval.pia_ca_llso.formal_audit import write_audit_tables, write_formal_source_lock
from goa_eval.pia_ca_llso.integration import CandidateAdapter, HistoryAdapter
from goa_eval.pia_ca_llso.io import ensure_output_dir, read_config, write_json, write_markdown
from goa_eval.pia_ca_llso.labeling import assign_level_labels, summarize_label_distribution
from goa_eval.pia_ca_llso.leakage import leakage_audit_rows
from goa_eval.pia_ca_llso.loop import suggest_next_run
from goa_eval.pia_ca_llso.method_registry import method_registry_records
from goa_eval.pia_ca_llso.multi_scenario_validation import run_multi_scenario_validation
from goa_eval.pia_ca_llso.paper_reproduction import DEFAULT_REPRODUCTION_METHODS, run_paper_reproduction_benchmark
from goa_eval.pia_ca_llso.report import render_candidate_report
from goa_eval.pia_ca_llso.training_data import build_training_data_from_db
from goa_eval.pia_ca_llso.transistor_level_adapter import build_transistor_level_netlists
from goa_eval.pia_ca_llso.validation_protocol import ValidationRunSpec


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
    benchmark.add_argument("--history-csv")
    benchmark.add_argument("--candidate-csv")
    benchmark.add_argument("--config")
    benchmark.add_argument("--output-dir", required=True)
    benchmark.add_argument("--strategies", default="random,ca_llso_raw_distance,pia_physics_distance,pia_capm_distance,adaptive_pia_capm,classifier_level_hybrid,active_uncertainty_diversity,active_influence_on_demand,literature_ensemble_hybrid")
    benchmark.add_argument("--target-score", type=float, default=80)
    benchmark.add_argument("--seed", type=int, default=42)
    benchmark.add_argument("--closed-loop", action="store_true")
    benchmark.add_argument("--evolution-dir")
    benchmark.set_defaults(handler=handle_pia_benchmark)

    contract = subparsers.add_parser("pia-export-contract")
    contract.add_argument("--output-dir", required=True)
    contract.set_defaults(handler=handle_pia_export_contract)

    render_transistor = subparsers.add_parser("pia-render-transistor-netlists")
    render_transistor.add_argument("--simulation-batch", required=True)
    render_transistor.add_argument("--template", required=True)
    render_transistor.add_argument("--config", default="config/pia_ca_llso_transistor_profile.yaml")
    render_transistor.add_argument("--output-dir", required=True)
    render_transistor.set_defaults(handler=handle_pia_render_transistor_netlists)

    train = subparsers.add_parser("pia-train-from-db")
    train.add_argument("--paper-db", type=Path, default=Path("data/paper_database"))
    train.add_argument("--history-root", type=Path, default=Path("outputs"))
    train.add_argument("--config", type=Path, default=Path("config/pia_ca_llso_goa_profile.yaml"))
    train.add_argument("--output-dir", type=Path, default=Path("outputs/pia_training_from_db"))
    train.add_argument("--optimization-dataset", type=Path, action="append", default=[])
    train.add_argument("--candidate-csv", type=Path)
    train.set_defaults(handler=handle_pia_train_from_db)

    # ---- pia-evolve ----
    evolve = subparsers.add_parser("pia-evolve", help="Run PIA-CA-LLSO closed-loop evolution")
    evolve.add_argument("--history-csv", required=True, type=str)
    evolve.add_argument("--candidate-csv", required=True, type=str)
    evolve.add_argument("--config", required=True, type=str)
    evolve.add_argument("--output-dir", required=True, type=str)
    evolve.add_argument("--strategy", default="classifier_level_hybrid", type=str)
    evolve.add_argument("--generations", type=int, default=None)
    evolve.add_argument("--offspring-per-generation", type=int, default=None)
    evolve.add_argument("--top-k", type=int, default=None)
    evolve.add_argument("--mode", type=str, default=None)
    evolve.add_argument("--simulation-results-dir", type=str, default=None)
    evolve.add_argument("--external-command", type=str, default=None)
    evolve.add_argument("--target-score", type=float, default=None)
    evolve.add_argument("--resume-from", type=str, default=None)
    evolve.add_argument("--resume-generation", type=int, default=None)
    evolve.add_argument("--audit-boundary", action="store_true")
    evolve.add_argument("--seed", type=int, default=42)
    evolve.set_defaults(handler=handle_pia_evolve)

    validate = subparsers.add_parser("pia-validate", help="Run PIA-CA-LLSO Phase 3 validation experiments")
    validate.add_argument("--protocol", default="config/pia_ca_llso_validation_protocol.yaml")
    validate.add_argument("--output-dir", default="outputs/pia_phase3_validation")
    validate.add_argument("--history-csv")
    validate.add_argument("--candidate-csv")
    validate.add_argument("--config")
    validate.add_argument("--methods")
    validate.add_argument("--seeds")
    validate.add_argument("--target-score", type=float)
    validate.add_argument("--top-k", type=int)
    validate.add_argument("--smoke", action="store_true")
    validate.add_argument("--multi-scenario", action="store_true")
    validate.add_argument("--max-runs", type=int, default=None)
    validate.add_argument("--case-pack")
    validate.add_argument("--case-pack-root")
    validate.add_argument("--strict-evidence", action="store_true")
    validate.add_argument("--export-case-pack-template", action="store_true")
    validate.set_defaults(handler=handle_pia_validate)


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
    if args.closed_loop:
        if not args.evolution_dir:
            raise ValueError("--evolution-dir is required with --closed-loop")
        run_closed_loop_benchmark(args.evolution_dir, output_dir, target_score=args.target_score)
        return 0
    if not args.history_csv or not args.candidate_csv:
        raise ValueError("--history-csv and --candidate-csv are required unless --closed-loop is set")
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


def handle_pia_render_transistor_netlists(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    config = read_config(args.config)
    simulation_batch = pd.read_csv(args.simulation_batch)
    netlists, manifest = build_transistor_level_netlists(
        simulation_batch,
        template_path=args.template,
        output_dir=output_dir,
        parameter_columns=config.get("parameter_columns", []),
    )
    netlists.to_csv(output_dir / "transistor_level_netlists.csv", index=False)
    write_json(output_dir / "transistor_level_netlist_manifest.json", manifest)
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


def handle_pia_evolve(args: argparse.Namespace) -> int:
    """Handle pia-evolve CLI command."""
    from goa_eval.pia_ca_llso.evolution import run_evolution_loop
    from goa_eval.pia_ca_llso.io import read_csv

    config = read_config(args.config)
    output_dir = ensure_output_dir(args.output_dir)

    if args.mode is not None:
        config.setdefault("simulation_executor", {})["mode"] = args.mode
    if args.external_command is not None:
        config.setdefault("simulation_executor", {})["external_command"] = args.external_command
    if args.simulation_results_dir is not None:
        config.setdefault("simulation_executor", {})["simulation_results_dir"] = args.simulation_results_dir
    if args.target_score is not None:
        config["target_score"] = args.target_score

    history = read_csv(args.history_csv)
    candidates = read_csv(args.candidate_csv)

    try:
        history = HistoryAdapter(history).adapt()
    except Exception:
        pass
    try:
        candidates = CandidateAdapter(candidates).adapt()
    except Exception:
        pass

    summary = run_evolution_loop(
        history=history,
        candidates=candidates,
        config=config,
        output_dir=output_dir,
        strategy=args.strategy,
        generations=args.generations,
        offspring_per_generation=args.offspring_per_generation,
        top_k=args.top_k,
        random_seed=args.seed,
        resume_from=args.resume_from,
        resume_generation=args.resume_generation,
    )
    if args.audit_boundary:
        audit = audit_evolution_outputs(output_dir)
        write_json(output_dir / "boundary_audit.json", audit)
        if not audit.get("passed", False):
            return 1

    print(str(output_dir.resolve()))
    return 0


def handle_pia_validate(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output_dir)
    if args.multi_scenario:
        protocol = read_config(args.protocol)
        config_path = args.config or protocol.get("config") or "config/pia_ca_llso_goa_profile.yaml"
        summary = run_multi_scenario_validation(
            protocol,
            output_dir,
            seeds=_parse_seed_list(args.seeds) if args.seeds else None,
            methods=_resolve_validation_methods(args.methods, protocol) if args.methods else None,
            top_k=args.top_k,
            target_score=args.target_score,
            config=read_config(config_path),
        )
        write_json(output_dir / "pia_validation_summary.json", summary)
        print(str(output_dir.resolve()))
        return 0

    if args.export_case_pack_template:
        from goa_eval.pia_ca_llso.case_pack import export_case_pack_template

        output_dir = export_case_pack_template(args.output_dir)
        print(str(output_dir.resolve()))
        return 0
    if args.case_pack or args.case_pack_root:
        from goa_eval.pia_ca_llso.case_pack_validation import run_case_pack_validation

        output_dir = ensure_output_dir(args.output_dir)
        run_case_pack_validation(
            args.case_pack,
            args.case_pack_root,
            output_dir,
            strict_evidence=args.strict_evidence,
            command_args=["pia-validate", *(_validation_command_args(args))],
        )
        print(str(output_dir.resolve()))
        return 0

    from goa_eval.pia_ca_llso.scenario_registry import load_scenario
    from goa_eval.pia_ca_llso.validation_protocol import expand_validation_grid, load_validation_protocol
    from goa_eval.pia_ca_llso.validation_report import render_validation_report
    from goa_eval.pia_ca_llso.validation_runner import run_validation_spec
    from goa_eval.pia_ca_llso.validation_statistics import compute_pairwise_win_rates, summarize_validation_runs

    protocol = load_validation_protocol(args.protocol)
    specs = expand_validation_grid(protocol)
    specs = _select_validation_specs(specs, protocol, smoke=args.smoke, max_runs=args.max_runs)
    scenario_entries = {
        entry["scenario_id"]: entry for entry in protocol["scenarios"]
        if isinstance(entry, dict) and "scenario_id" in entry
    }
    scenario_cache: dict[str, dict] = {}
    run_summaries = []
    leakage_rows = []
    for spec in specs:
        if spec.scenario_id not in scenario_cache:
            scenario_cache[spec.scenario_id] = load_scenario(scenario_entries[spec.scenario_id])
            leakage_rows.extend(
                leakage_audit_rows(spec.scenario_id, scenario_cache[spec.scenario_id]["candidates"])
            )
        run_summaries.append(
            run_validation_spec(
                spec,
                scenario_cache[spec.scenario_id],
                output_dir,
                smoke=args.smoke,
            )
        )

    run_frame = pd.DataFrame(run_summaries)
    summary_frame = summarize_validation_runs(run_summaries)
    win_rate_frame = compute_pairwise_win_rates(run_frame, baseline="random")
    fairness_frame, leakage_frame, scenario_frame = write_audit_tables(
        output_dir,
        run_summaries=run_summaries,
        scenario_bundles=scenario_cache,
        leakage_rows=leakage_rows,
    )
    run_frame.to_csv(output_dir / "validation_runs.csv", index=False)
    summary_frame.to_csv(output_dir / "validation_summary.csv", index=False)
    win_rate_frame.to_csv(output_dir / "pairwise_win_rates.csv", index=False)
    write_json(output_dir / "method_registry.json", {"methods": method_registry_records()})
    write_json(
        output_dir / "validation_summary.json",
        {
            "protocol": protocol.get("name", "pia_ca_llso_phase3_validation"),
            "run_count": len(run_summaries),
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
            "summary": summary_frame.to_dict(orient="records"),
            "fairness_audit_rows": len(fairness_frame),
            "leakage_audit_passed": bool(leakage_frame["leakage_check_passed"].all()) if not leakage_frame.empty else True,
            "scenario_count": len(scenario_frame),
        },
    )
    write_markdown(
        output_dir / "experimental_validation_report.md",
        render_validation_report(protocol, run_frame, summary_frame, win_rate_frame),
    )
    write_markdown(
        output_dir / "formal_validation_report.md",
        render_validation_report(protocol, run_frame, summary_frame, win_rate_frame, formal=True),
    )
    write_formal_source_lock(
        output_dir,
        protocol=protocol,
        run_summaries=run_summaries,
        scenario_bundles=scenario_cache,
        command_args=["pia-validate", *(_validation_command_args(args))],
    )
    if args.smoke:
        _run_paper_reproduction_sidecar(args, protocol, output_dir)
    print(str(output_dir.resolve()))
    return 0


def _run_paper_reproduction_sidecar(args: argparse.Namespace, protocol: dict, output_dir: Path) -> None:
    scenario = _resolve_validation_scenario(protocol, smoke=args.smoke)
    history_csv = args.history_csv or scenario.get("history_csv") or protocol.get("history_csv")
    candidate_csv = args.candidate_csv or scenario.get("candidate_csv") or protocol.get("candidate_csv")
    if not history_csv or not candidate_csv:
        return
    config_path = args.config or scenario.get("config") or protocol.get("config") or "config/pia_ca_llso_goa_profile.yaml"
    history = HistoryAdapter().load(history_csv)
    candidates = CandidateAdapter().load(candidate_csv)
    target_score = float(args.target_score if args.target_score is not None else protocol.get("target_score", 80.0))
    top_k = int(args.top_k if args.top_k is not None else protocol.get("top_k", 4))
    methods = [
        method
        for method in _resolve_validation_methods(args.methods, protocol, smoke=args.smoke)
        if method in DEFAULT_REPRODUCTION_METHODS
    ] or list(DEFAULT_REPRODUCTION_METHODS)
    run_paper_reproduction_benchmark(
        history,
        candidates,
        output_dir,
        methods=methods,
        target_score=target_score,
        top_k=top_k,
        config=read_config(config_path),
    )


def _select_validation_specs(
    specs: list[ValidationRunSpec],
    protocol: dict,
    smoke: bool,
    max_runs: int | None,
) -> list[ValidationRunSpec]:
    selected = specs
    if smoke:
        first_scenario = str(protocol["scenarios"][0]["scenario_id"])
        first_two_seeds = {int(seed) for seed in protocol["seeds"][:2]}
        smoke_ablations = {
            str(ablation) for ablation in protocol.get("smoke_ablations", ["full"])
        }
        selected = [
            ValidationRunSpec(
                scenario_id=spec.scenario_id,
                method=spec.method,
                ablation=spec.ablation,
                seed=spec.seed,
                budget=8,
                target_score=spec.target_score,
            )
            for spec in specs
            if (
                spec.scenario_id == first_scenario
                and spec.seed in first_two_seeds
                and spec.budget == protocol["budgets"][0]
                and spec.ablation in smoke_ablations
            )
        ]
    if max_runs is not None:
        selected = selected[: int(max_runs)]
    return selected


def _validation_command_args(args: argparse.Namespace) -> list[str]:
    values = []
    for name in [
        "protocol",
        "output_dir",
        "case_pack",
        "case_pack_root",
    ]:
        value = getattr(args, name, None)
        if value:
            values.extend([f"--{name.replace('_', '-')}", str(value)])
    for name in ["smoke", "strict_evidence", "export_case_pack_template"]:
        if getattr(args, name, False):
            values.append(f"--{name.replace('_', '-')}")
    if args.max_runs is not None:
        values.extend(["--max-runs", str(args.max_runs)])
    return values


def _resolve_validation_scenario(protocol: dict, smoke: bool) -> dict:
    scenarios = protocol.get("smoke_scenarios" if smoke else "scenarios", [])
    if isinstance(scenarios, list) and scenarios:
        first = scenarios[0]
        return first if isinstance(first, dict) else {}
    scenarios = protocol.get("scenarios", [])
    if isinstance(scenarios, list) and scenarios:
        first = scenarios[0]
        return first if isinstance(first, dict) else {}
    return {}


def _resolve_validation_methods(methods_arg: str | None, protocol: dict, smoke: bool = False) -> list[str]:
    if methods_arg:
        return [method.strip() for method in methods_arg.split(",") if method.strip()]
    if smoke:
        smoke_methods = protocol.get("smoke_methods")
        if isinstance(smoke_methods, list) and smoke_methods:
            return [str(method) for method in smoke_methods]
    configured = protocol.get("methods")
    if isinstance(configured, list) and configured and not smoke:
        return [str(method) for method in configured]
    return list(DEFAULT_REPRODUCTION_METHODS)


def _parse_seed_list(value: str) -> list[int]:
    seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    return seeds or [42]
