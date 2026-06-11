from __future__ import annotations

from pathlib import Path


def write_paper_digitization_report(path: Path, *, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = [f"# {title}", "", *lines, "", "Boundary: paper digitized data is weak-label, simulation_only evidence."]
    path.write_text("\n".join(content) + "\n", encoding="utf-8")
