"""Fairness audit and source-lock helpers for formal validation runs."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from goa_eval.pia_ca_llso import DATA_SOURCE, ENGINEERING_VALIDITY
from goa_eval.pia_ca_llso.io import write_json


def file_sha256(path: str | Path | None) -> str:
    if not path:
        return ""
    resolved = Path(path)
    if not resolved.exists():
        return ""
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_scenario_manifest_rows(scenario_bundles: Mapping[str, dict]) -> list[dict[str, Any]]:
    rows = []
    for scenario_id, bundle in sorted(scenario_bundles.items()):
        rows.append(
            {
                "scenario_id": scenario_id,
                "history_csv": bundle.get("history_csv", ""),
                "candidate_csv": bundle.get("candidate_csv", ""),
                "config_hash": object_sha256(bundle.get("config", {})),
                "history_hash": file_sha256(bundle.get("history_csv")),
                "candidate_pool_hash": file_sha256(bundle.get("candidate_csv")),
                "source_type": bundle.get("source_type", ""),
                "claim_boundary": bundle.get("claim_boundary", ""),
                "data_source": DATA_SOURCE,
                "engineering_validity": ENGINEERING_VALIDITY,
                "must_resimulate": True,
            }
        )
    return rows


def build_fairness_audit_rows(run_summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for summary in run_summaries:
        rows.append(
            {
                "scenario_id": summary.get("scenario_id"),
                "method": summary.get("method"),
                "ablation": summary.get("ablation"),
                "budget": summary.get("budget"),
                "seed": summary.get("seed"),
                "target_score": summary.get("target_score"),
                "history_hash": summary.get("history_hash", ""),
                "candidate_pool_hash": summary.get("candidate_pool_hash", ""),
                "scoring_config_hash": summary.get("scoring_config_hash", ""),
                "result_source": summary.get("result_source", ""),
                "leakage_check_passed": bool(summary.get("leakage_check_passed", False)),
                "boundary_audit_passed": bool(summary.get("boundary_audit_passed", False)),
                "evidence_status": summary.get("evidence_status", ""),
                "data_source": DATA_SOURCE,
                "engineering_validity": ENGINEERING_VALIDITY,
                "must_resimulate": True,
            }
        )
    return rows


def write_formal_source_lock(
    output_dir: Path,
    *,
    protocol: Mapping[str, Any],
    run_summaries: Sequence[Mapping[str, Any]],
    scenario_bundles: Mapping[str, dict],
    command_args: Sequence[str] | None = None,
) -> dict[str, Any]:
    lock = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(output_dir),
        "command_args": list(command_args or []),
        "protocol_hash": object_sha256(protocol),
        "scenario_count": len(scenario_bundles),
        "run_count": len(run_summaries),
        "input_hashes": build_scenario_manifest_rows(scenario_bundles),
        "output_files": sorted(
            str(path.relative_to(output_dir)).replace("\\", "/")
            for path in output_dir.rglob("*")
            if path.is_file()
        ),
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": True,
    }
    write_json(output_dir / "source_lock.json", lock)
    return lock


def write_audit_tables(
    output_dir: Path,
    *,
    run_summaries: Sequence[Mapping[str, Any]],
    scenario_bundles: Mapping[str, dict],
    leakage_rows: Sequence[Mapping[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fairness = pd.DataFrame(build_fairness_audit_rows(run_summaries))
    leakage = pd.DataFrame(list(leakage_rows))
    scenarios = pd.DataFrame(build_scenario_manifest_rows(scenario_bundles))
    fairness.to_csv(output_dir / "fairness_audit.csv", index=False)
    leakage.to_csv(output_dir / "leakage_audit.csv", index=False)
    scenarios.to_csv(output_dir / "scenario_manifest.csv", index=False)
    return fairness, leakage, scenarios


def _git_commit(output_dir: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=output_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except Exception:
        return ""
