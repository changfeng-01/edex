from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from goa_eval.product_demo.artifact_collector import collect_artifacts, write_input_snapshot
from goa_eval.product_demo.dashboard_export import write_dashboard_exports
from goa_eval.product_demo.figures import write_figures
from goa_eval.product_demo.report import write_reports
from goa_eval.product_demo.schemas import DIRECTORIES
from goa_eval.product_demo.tables import write_tables


def run_product_demo(
    input_dir: Path | str,
    output_dir: Path | str,
    case_id: str,
    evidence_boundary: Mapping[str, Any] | None = None,
) -> Path:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    case_dir = output_path / case_id
    dirs = _prepare_dirs(case_dir)
    artifacts = collect_artifacts(input_path, evidence_boundary=evidence_boundary)
    write_input_snapshot(artifacts, dirs["input_snapshot"], case_id)
    table_paths = write_tables(artifacts, dirs, case_id)
    figure_paths = write_figures(artifacts, dirs["figures"], case_id)
    write_dashboard_exports(artifacts, dirs["dashboard"], case_id, table_paths, figure_paths)
    write_reports(artifacts, dirs["report"], case_id, table_paths, figure_paths)
    return case_dir


def _prepare_dirs(case_dir: Path) -> dict[str, Path]:
    dirs = {key: case_dir / name for key, name in DIRECTORIES.items()}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs
