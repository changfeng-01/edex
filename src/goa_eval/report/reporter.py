from __future__ import annotations

from pathlib import Path


REPORT_WARNING_LINES = [
    "This report is generated from mock waveform data for workflow validation only.",
    "It must not be interpreted as a real circuit performance conclusion.",
]

SIMULATION_NOTICE_LINES = [
    "This report is generated from simulation waveform data.",
    "It should be interpreted only within the limits of the supplied waveform CSV.",
]


def write_report_md(
    path: Path,
    *,
    summary: dict,
    input_design_path: Path | list[Path],
    metrics_path: Path,
    manifest_path: Path,
    figure_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opening = REPORT_WARNING_LINES if summary.get("data_source") == "mock" else SIMULATION_NOTICE_LINES
    lines = [
        *opening,
        "",
        "# 8T1C / GOA Workflow Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- data_source: `{summary['data_source']}`",
        f"- engineering_validity: `{summary['engineering_validity']}`",
        f"- input_design_path: `{_display_path(input_design_path)}`",
        f"- versions: {', '.join(summary.get('versions', []))}",
        "",
        "## Outputs",
        "",
        f"- metrics: `{metrics_path.as_posix()}`",
        f"- summary: `summary.json`",
        f"- manifest: `{manifest_path.as_posix()}`",
        f"- comparison_figure: `{figure_path.as_posix()}`",
        "",
        "## Hard Checks",
        "",
    ]
    checks = summary.get("hard_checks", {})
    if checks:
        for version, items in checks.items():
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(items.items()))
            lines.append(f"- {version}: {rendered}")
    else:
        lines.append("- No hard checks were produced.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _display_path(value: Path | list[Path]) -> str:
    if isinstance(value, list):
        return ", ".join(str(path) for path in value)
    return str(value)
