from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


def build_preflight_report(
    *,
    pdk_root: Path,
    ngspice: Path,
    output_dir: Path,
    mock_if_unavailable: bool = False,
) -> dict[str, Any]:
    pdk_exists = pdk_root.exists()
    ngspice_exists = ngspice.exists()
    can_run = pdk_exists and ngspice_exists
    if can_run:
        status = "ready_for_real_ngspice"
    elif mock_if_unavailable:
        status = "skipped_missing_toolchain"
    else:
        status = "blocked_missing_toolchain"
    return {
        "schema_version": SCHEMA_VERSION,
        "result_version": RESULT_VERSION,
        "experiment": "sky130_ngspice",
        "branch_policy": "experimental_branch_only",
        "status": status,
        "can_run_real_ngspice": can_run,
        "mock_if_unavailable": bool(mock_if_unavailable),
        "pdk_root": str(pdk_root),
        "pdk_root_exists": pdk_exists,
        "ngspice": str(ngspice),
        "ngspice_exists": ngspice_exists,
        "output_dir": str(output_dir),
        "tracked_tool_policy": "external_or_local_ignored_only",
        "ignored_paths": ["tools/", "outputs/", "runs/", "tmp_outputs/"],
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "note": "This preflight records whether local SKY130/ngspice assets are available; it does not claim physical validation.",
    }


def run_sky130_experiment_preflight(
    *,
    pdk_root: Path,
    ngspice: Path,
    output_dir: Path,
    mock_if_unavailable: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_preflight_report(
        pdk_root=pdk_root,
        ngspice=ngspice,
        output_dir=output_dir,
        mock_if_unavailable=mock_if_unavailable,
    )
    (output_dir / "sky130_experiment_preflight.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "sky130_ngspice_experiment.md").write_text(_markdown_report(report), encoding="utf-8")
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# SKY130 / ngspice Experiment Branch",
        "",
        f"- status: `{report['status']}`",
        f"- can_run_real_ngspice: `{report['can_run_real_ngspice']}`",
        f"- pdk_root: `{report['pdk_root']}`",
        f"- ngspice: `{report['ngspice']}`",
        f"- data_source: `{report['data_source']}`",
        f"- engineering_validity: `{report['engineering_validity']}`",
        f"- tracked_tool_policy: `{report['tracked_tool_policy']}`",
        "",
        "This branch keeps SKY130 / ngspice work experimental. Local PDK and simulator assets must stay outside tracked source or under ignored paths such as `tools/`.",
        "",
        "The output is simulation_only and not physical validation.",
        "",
        "## Next Step",
        "",
    ]
    if report["can_run_real_ngspice"]:
        lines.append("Run the small SKY130 smoke workflow, export waveform CSV, then feed the CSV through `evaluate-real` and `optimize-loop`.")
    elif report["mock_if_unavailable"]:
        lines.append("Toolchain assets were not found, so the real ngspice step was skipped. Use this report to verify branch wiring without committing local tools.")
    else:
        lines.append("Install or point to local SKY130 PDK and ngspice assets, then rerun with valid paths.")
    lines.append("")
    return "\n".join(lines)
