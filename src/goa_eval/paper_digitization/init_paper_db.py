from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.io_utils import write_json
from goa_eval.paper_digitization.schemas import (
    EXTRACTION_TARGETS,
    LITERATURE_CLAIM_BOUNDARY,
    PAPER_CASE_COLUMNS,
    PAPER_DIGITIZATION_SCHEMA_VERSION,
    PAPER_LEADERBOARD_COLUMNS,
    PAPER_METADATA,
    PAPER_PARAMS_LONG_COLUMNS,
    PAPER_WAVEFORM_INDEX_COLUMNS,
)


RAW_FIGURE_DIRS = {
    "you2024_10t2c_scan_driver": ["fig6", "fig7", "fig9"],
    "song2022_dual_gated_sr": ["fig8"],
    "zhou2025_31inch_goa": ["fig7", "fig9"],
}


def initialize_paper_database(root: Path = Path(".")) -> list[Path]:
    written: list[Path] = []
    papers_root = root / "papers"
    for meta in PAPER_METADATA:
        paper_dir = papers_root / meta["paper_id"]
        paper_dir.mkdir(parents=True, exist_ok=True)
        metadata = _paper_metadata_payload(meta)
        extraction_plan = _extraction_plan_payload(meta["paper_id"])
        metadata_path = paper_dir / "paper_metadata.yaml"
        plan_path = paper_dir / "extraction_plan.yaml"
        metadata_path.write_text(yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), encoding="utf-8")
        plan_path.write_text(yaml.safe_dump(extraction_plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
        written.extend([metadata_path, plan_path])

    for paper_id, figure_ids in RAW_FIGURE_DIRS.items():
        for figure_id in figure_ids:
            directory = root / "data" / "paper_digitized_raw" / paper_id / figure_id
            directory.mkdir(parents=True, exist_ok=True)
            keep = directory / ".gitkeep"
            if not keep.exists():
                keep.write_text("", encoding="utf-8")
            written.append(keep)

    database_root = root / "data" / "paper_database"
    database_root.mkdir(parents=True, exist_ok=True)
    _write_empty_csv(database_root / "paper_cases.csv", PAPER_CASE_COLUMNS)
    _write_empty_csv(database_root / "paper_params_long.csv", PAPER_PARAMS_LONG_COLUMNS)
    _write_empty_csv(database_root / "paper_waveform_index.csv", PAPER_WAVEFORM_INDEX_COLUMNS)
    _write_empty_csv(database_root / "paper_goa_leaderboard.csv", PAPER_LEADERBOARD_COLUMNS)
    write_json(
        database_root / "paper_database_summary.json",
        {
            "schema_version": PAPER_DIGITIZATION_SCHEMA_VERSION,
            "paper_count": len(PAPER_METADATA),
            "case_count": 0,
            "status": "initialized",
            "notes": [
                "No paper numerical data is fabricated by initialization.",
                "Manual extraction or WebPlotDigitizer CSV input is required before evaluation.",
            ],
        },
    )
    written.extend(
        [
            database_root / "paper_cases.csv",
            database_root / "paper_params_long.csv",
            database_root / "paper_waveform_index.csv",
            database_root / "paper_goa_leaderboard.csv",
            database_root / "paper_database_summary.json",
        ]
    )
    return written


def _paper_metadata_payload(meta: dict) -> dict:
    return {
        "schema_version": PAPER_DIGITIZATION_SCHEMA_VERSION,
        "paper_id": meta["paper_id"],
        "title": meta["title"],
        "authors": meta["authors"],
        "year": meta["year"],
        "venue": meta["venue"],
        "doi": meta["doi"],
        "url": meta["url"],
        "main_role": meta["main_role"],
        "source_priority": meta["source_priority"],
        "circuit_type": meta["circuit_type"],
        "device_type": meta["device_type"],
        "topology_id": meta["topology_id"],
        "data_use": ["topology_reference", "parameter_table", "waveform_digitization", "weak_label"],
        "claim_boundary": LITERATURE_CLAIM_BOUNDARY,
        "notes": "Bibliographic metadata verified from attached PDF metadata/text; numerical extraction remains manual.",
    }


def _extraction_plan_payload(paper_id: str) -> dict:
    targets = []
    for target_id, location, source_type, expected_outputs, manual_steps in EXTRACTION_TARGETS[paper_id]:
        targets.append(
            {
                "target_id": target_id,
                "source_location": location,
                "source_type": source_type,
                "expected_outputs": expected_outputs,
                "manual_steps": manual_steps,
                "status": "pending",
                "notes": "Use null or TODO_NEEDS_MANUAL_EXTRACTION when the value is not directly supported by text/table/caption/WPD CSV.",
            }
        )
    return {"schema_version": PAPER_DIGITIZATION_SCHEMA_VERSION, "paper_id": paper_id, "targets": targets}


def _write_empty_csv(path: Path, columns: list[str]) -> None:
    pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize CircuitPilot paper digitization database templates.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root. Defaults to current directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    written = initialize_paper_database(args.root)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
