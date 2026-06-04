from __future__ import annotations

import argparse
import re
from pathlib import Path

from goa_eval.cli_commands.common import output_path
from goa_eval.config import load_configs
from goa_eval.evaluation.feature_extractor import extract_waveform_features
from goa_eval.evaluation.mock_waveform import generate_mock_waveform
from goa_eval.evaluation.scoring import compute_metric_results
from goa_eval.io_utils import copy_initial_raw_inputs, ensure_run_dirs, extract_archives, to_jsonable, write_json
from goa_eval.parsers.design_parser import build_design_version, discover_design_roots
from goa_eval.parsers.mapping_parser import parse_mapping
from goa_eval.parsers.metric_table_parser import parse_metric_table
from goa_eval.parsers.netlist_parser import parse_netlist
from goa_eval.parsers.waveform_parser import read_waveform_csv
from goa_eval.report.manifest import write_run_manifest
from goa_eval.report.markdown_report import write_markdown_report
from goa_eval.report.reporter import write_report_md
from goa_eval.report.summary_writer import write_metric_table, write_metrics_csv, write_summary_json
from goa_eval.visualization.comparison_plotter import plot_v1_v8_comparison
from goa_eval.visualization.metric_plotter import plot_voh_bar
from goa_eval.visualization.version_compare_plotter import plot_timing_overview
from goa_eval.visualization.waveform_plotter import plot_waveform_overview


def register(subparsers: argparse._SubParsersAction) -> None:
    for name, handler in [
        ("extract", handle_extract),
        ("parse", handle_parse),
        ("evaluate", handle_evaluate),
        ("all", handle_all),
    ]:
        cmd = subparsers.add_parser(name)
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
        cmd.set_defaults(handler=handler)


def handle_extract(args: argparse.Namespace) -> int:
    extract_archives(Path(args.raw), output_path(args))
    return 0


def handle_parse(args: argparse.Namespace) -> int:
    config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
    out = output_path(args)
    ensure_run_dirs(out)
    designs = parse_designs(Path(args.input))
    write_design_summary(out, designs)
    write_netlist_parse_json(out, designs)
    specs = _parse_metric_table_if_available(Path(args.raw))
    if specs:
        write_metric_table(out, specs)
    return 0


def handle_evaluate(args: argparse.Namespace) -> int:
    config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
    out = output_path(args)
    if args.design:
        out.mkdir(parents=True, exist_ok=True)
        design = parse_single_design(Path(args.design))
        comparison_designs = comparison_designs_for(design)
        return evaluate_designs_flat(out, [design], comparison_designs, config, thresholds, args.mock_waveform, out.name, args, design.root_dir)
    ensure_run_dirs(out)
    designs = parse_designs(Path(args.input))
    return evaluate_designs(out, designs, config, thresholds, args.mock_waveform, "dev_run", args, Path(args.input))


def handle_all(args: argparse.Namespace) -> int:
    root = Path.cwd()
    copy_initial_raw_inputs(root)
    raw = Path(args.raw)
    extracted = Path(args.input)
    extract_archives(raw, extracted)
    config, thresholds = load_configs(Path(args.config), Path(args.thresholds))
    out = output_path(args)
    ensure_run_dirs(out)
    designs = parse_designs(extracted)
    write_design_summary(out, designs)
    write_netlist_parse_json(out, designs)
    specs = _parse_metric_table_if_available(raw)
    if specs:
        write_metric_table(out, specs)
    return evaluate_designs(out, designs, config, thresholds, args.mock_waveform, out.name, args, extracted)


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
    preferred = raw_dir / "璇勪环鎸囨爣琛?html"
    if preferred.exists():
        return preferred
    matches = list(raw_dir.glob("*.html"))
    return matches[0] if matches else None
