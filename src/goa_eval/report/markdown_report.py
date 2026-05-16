from pathlib import Path

from goa_eval.report.summary_writer import MOCK_WARNING_CN


def write_markdown_report(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 8T1C / GOA Evaluation Summary",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- data_source: `{summary['data_source']}`",
        f"- engineering_validity: `{summary['engineering_validity']}`",
        f"- versions: {', '.join(summary['versions'])}",
        "",
    ]
    if summary["data_source"] == "mock":
        lines.extend([f"> {MOCK_WARNING_CN}", ""])
    lines.append("## Hard Checks")
    for version, checks in summary.get("hard_checks", {}).items():
        lines.append(f"- {version}: {checks}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
