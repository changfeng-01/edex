"""Scenario registry and real case-pack validation for Phase 3 PIA runs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from goa_eval.pia_ca_llso.io import read_config


BOUNDARY = {
    "data_source": "real_simulation_csv",
    "engineering_validity": "simulation_only",
    "must_resimulate": True,
}


def load_scenario(scenario_entry: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    entry, base_dir, from_manifest = _normalize_entry(scenario_entry)
    entry.setdefault("boundary", dict(BOUNDARY))
    entry.setdefault("source_type", "local_fixture")
    _validate_manifest_contract(entry)

    history_csv = _resolve(base_dir, entry["history_csv"])
    candidate_csv = _resolve(base_dir, entry["candidate_csv"])
    config_path = _resolve(base_dir, entry["config"])
    for path in [history_csv, candidate_csv, config_path]:
        if not path.exists():
            raise FileNotFoundError(str(path))

    bundle = {
        "scenario_id": str(entry["scenario_id"]),
        "history": pd.read_csv(history_csv),
        "candidates": pd.read_csv(candidate_csv),
        "config": read_config(config_path),
        "history_csv": str(history_csv),
        "candidate_csv": str(candidate_csv),
        "config_path": str(config_path),
        "boundary": dict(entry.get("boundary", BOUNDARY)),
        "source_type": str(entry.get("source_type", "local_fixture")),
        "claim_boundary": str(
            entry.get(
                "claim_boundary",
                "simulation-only benchmark scenario; not physical validation",
            )
        ),
    }
    if from_manifest and "result_dirs" in entry:
        bundle["result_dirs"] = [str(_resolve(base_dir, item)) for item in entry["result_dirs"]]
    validate_scenario_bundle(bundle)
    return bundle


def validate_scenario_bundle(bundle: Mapping[str, Any]) -> None:
    required = [
        "scenario_id",
        "history",
        "candidates",
        "config",
        "history_csv",
        "candidate_csv",
        "boundary",
        "source_type",
    ]
    missing = [key for key in required if key not in bundle]
    if missing:
        raise ValueError(f"scenario bundle missing required fields: {', '.join(missing)}")
    if bundle["history"].empty:
        raise ValueError("scenario history is empty")
    if bundle["candidates"].empty:
        raise ValueError("scenario candidates are empty")
    for field, expected in BOUNDARY.items():
        actual = bundle["boundary"].get(field)
        if actual != expected:
            raise ValueError(f"boundary.{field} must be {expected}")


def _normalize_entry(scenario_entry: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], Path, bool]:
    if isinstance(scenario_entry, Mapping):
        entry = dict(scenario_entry)
        manifest = entry.get("manifest") or entry.get("manifest_path")
        if manifest:
            return _load_manifest(Path(str(manifest)))
        return entry, Path.cwd(), False
    return _load_manifest(Path(scenario_entry))


def _load_manifest(path: Path) -> tuple[dict[str, Any], Path, bool]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    entry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(entry), path.parent, True


def _validate_manifest_contract(entry: Mapping[str, Any]) -> None:
    required = ["scenario_id", "history_csv", "candidate_csv", "config", "boundary"]
    missing = [key for key in required if key not in entry]
    if missing:
        raise ValueError(f"scenario manifest missing required fields: {', '.join(missing)}")
    boundary = entry.get("boundary", {})
    for field, expected in BOUNDARY.items():
        if boundary.get(field) != expected:
            raise ValueError(f"boundary.{field} must be {expected}")
    source_type = str(entry.get("source_type", "real_simulation_csv"))
    claim_source_type = str(entry.get("claim_source_type", source_type))
    if source_type == "paper_digitized" and claim_source_type == "real_simulation_csv":
        raise ValueError("paper_digitized scenarios cannot be claimed as real_simulation_csv")
    if source_type == "real_simulation_csv" and not entry.get("result_dirs"):
        raise ValueError("real_simulation_csv case packs require result_dirs")


def _resolve(base_dir: Path, raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    return Path.cwd() / path
