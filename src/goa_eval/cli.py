from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

import pandas as pd

from goa_eval.config import load_configs
from goa_eval.batch_eval import run_batch_evaluation
from goa_eval.evaluation.feature_extractor import extract_waveform_features
from goa_eval.evaluation.mock_waveform import generate_mock_waveform
from goa_eval.evaluation.scoring import compute_metric_results
from goa_eval.io_utils import copy_initial_raw_inputs, ensure_run_dirs, extract_archives, to_jsonable, write_json
from goa_eval.optimizer import load_param_space, propose_candidates, write_candidate_outputs
from goa_eval.parsers.design_parser import build_design_version, discover_design_roots
from goa_eval.parsers.mapping_parser import parse_mapping
from goa_eval.parsers.metric_table_parser import parse_metric_table
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.parsers.waveform_parser import read_waveform_csv
from goa_eval.report.manifest import write_run_manifest
from goa_eval.report.markdown_report import write_markdown_report
from goa_eval.report.reporter import write_report_md
from goa_eval.report.summary_writer import write_metric_table, write_metrics_csv, write_summary_json
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown
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
        specs = parse_metric_table(_metric_table_path(Path(args.raw)))
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
        specs = parse_metric_table(_metric_table_path(raw))
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
    if args.command == "evaluate-batch":
        run_batch_evaluation(runs_dir=Path(args.runs_dir), output_dir=Path(args.output_dir))
        return 0
    if args.command == "propose-candidates":
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        score = json.loads(Path(args.score).read_text(encoding="utf-8")) if args.score else {}
        metrics = pd.read_csv(Path(args.metrics)) if args.metrics else pd.DataFrame()
        recommendations = build_recommendations(summary, score, metrics)
        candidates = propose_candidates(load_param_space(Path(args.param_space)), recommendations)
        write_candidate_outputs(candidates, csv_path=Path(args.output_csv), markdown_path=Path(args.output_md))
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
    recommend = sub.add_parser("recommend")
    recommend.add_argument("--summary", required=True)
    recommend.add_argument("--score")
    recommend.add_argument("--metrics")
    recommend.add_argument("--output", default="outputs/recommendations.md")
    batch = sub.add_parser("evaluate-batch")
    batch.add_argument("--runs-dir", required=True)
    batch.add_argument("--output-dir", default="outputs_batch")
    candidates = sub.add_parser("propose-candidates")
    candidates.add_argument("--summary", required=True)
    candidates.add_argument("--score")
    candidates.add_argument("--metrics")
    candidates.add_argument("--param-space", required=True)
    candidates.add_argument("--output-csv", default="outputs/next_candidates.csv")
    candidates.add_argument("--output-md", default="outputs/next_candidates.md")
    return parser


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


def _metric_table_path(raw_dir: Path) -> Path:
    preferred = raw_dir / "评价指标表.html"
    if preferred.exists():
        return preferred
    matches = list(raw_dir.glob("*.html"))
    return matches[0] if matches else preferred


if __name__ == "__main__":
    raise SystemExit(main())
