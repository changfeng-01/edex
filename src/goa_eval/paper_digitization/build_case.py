from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

import yaml

from goa_eval.paper_digitization.quality_check import run_quality_check
from goa_eval.paper_digitization.schemas import (
    ENGINEERING_VALIDITY,
    PAPER_CLAIM_BOUNDARY,
    PAPER_DIGITIZED_DATA_SOURCE,
    SOURCE_TYPE_PAPER_DIGITIZED,
)
from goa_eval.paper_digitization.wpd_import import convert_wpd_csv


def build_paper_case(
    *,
    case_config_path: Path,
    output_root: Path = Path("data/paper_digitized"),
) -> Path:
    config = yaml.safe_load(case_config_path.read_text(encoding="utf-8")) or {}
    case_id = _required(config, "case_id")
    case_dir = output_root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    waveform_path = config.get("waveform_path")
    wpd_raw_path = config.get("wpd_raw_path")
    if waveform_path:
        shutil.copy2(Path(waveform_path), case_dir / "waveform.csv")
        quality = run_quality_check(
            waveform_path=case_dir / "waveform.csv",
            case_id=case_id,
            high_threshold=float(config.get("high_threshold", 5.0)),
            low_threshold=float(config.get("low_threshold", 1.0)),
            supply_min_v=config.get("supply_min_v"),
            supply_max_v=config.get("supply_max_v"),
            output_path=case_dir / "digitization_quality.json",
        )
    elif wpd_raw_path:
        convert_wpd_csv(
            input_path=Path(wpd_raw_path),
            output_path=case_dir / "waveform.csv",
            time_unit=str(config.get("time_unit", "s")),
            voltage_unit=str(config.get("voltage_unit", "V")),
            curve_map_path=Path(config["curve_map_path"]) if config.get("curve_map_path") else None,
            resample_step=config.get("resample_step"),
            quality_path=case_dir / "digitization_quality.json",
        )
        quality = run_quality_check(
            waveform_path=case_dir / "waveform.csv",
            case_id=case_id,
            high_threshold=float(config.get("high_threshold", 5.0)),
            low_threshold=float(config.get("low_threshold", 1.0)),
            supply_min_v=config.get("supply_min_v"),
            supply_max_v=config.get("supply_max_v"),
            output_path=case_dir / "digitization_quality.json",
        )
    else:
        raise ValueError("case_config.yaml must include waveform_path or wpd_raw_path")

    _copy_optional(config.get("internal_waveform_path"), case_dir / "internal_waveform.csv")
    _copy_optional(config.get("paper_params_path"), case_dir / "paper_params.yaml", default={})
    _copy_optional(config.get("paper_metadata_path"), case_dir / "paper_metadata.yaml", default={})

    metadata = simulation_metadata_payload(config, quality=quality)
    (case_dir / "simulation_metadata.yaml").write_text(
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return case_dir


def simulation_metadata_payload(config: dict[str, Any], *, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "adapter": "paper-digitization",
        "source_type": SOURCE_TYPE_PAPER_DIGITIZED,
        "weak_label": True,
        "data_source": PAPER_DIGITIZED_DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "claim_boundary": PAPER_CLAIM_BOUNDARY,
        "paper_id": config.get("paper_id"),
        "figure_id": config.get("figure_id"),
        "table_id": config.get("table_id"),
        "case_id": config.get("case_id"),
        "digitization_tool": config.get("digitization_tool", "WebPlotDigitizer_or_Engauge_manual_csv"),
        "manual_digitization_required": bool(config.get("manual_digitization_required", True)),
        "quality_status": (quality or {}).get("quality_status"),
        "notes": config.get("notes", ""),
    }


def _copy_optional(source: str | None, target: Path, *, default: dict | None = None) -> None:
    if source:
        shutil.copy2(Path(source), target)
    elif default is not None and not target.exists():
        target.write_text(yaml.safe_dump(default, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _required(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if value in (None, ""):
        raise ValueError(f"case_config.yaml missing required field: {key}")
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a standard paper digitized case directory.")
    parser.add_argument("--case-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/paper_digitized"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    case_dir = build_paper_case(case_config_path=args.case_config, output_root=args.output_root)
    print(case_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
