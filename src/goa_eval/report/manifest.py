from __future__ import annotations

from pathlib import Path
import datetime as dt
import subprocess
import sys

from goa_eval.io_utils import sha256_file, write_json


def write_run_manifest(
    path: Path,
    *,
    run_id: str,
    input_design_path: Path | list[Path],
    config: dict,
    thresholds: dict,
    data_source: str,
    engineering_validity: str,
) -> dict:
    manifest = {
        "run_id": run_id,
        "run_time": dt.datetime.now().isoformat(timespec="seconds"),
        "input_design_path": _path_value(input_design_path),
        "input_file_hashes": _hash_inputs(input_design_path),
        "config": config,
        "thresholds": thresholds,
        "command": "python -m goa_eval.cli " + " ".join(sys.argv[1:]),
        "code_version_or_git_commit": _git_commit(),
        "data_source": data_source,
        "engineering_validity": engineering_validity,
    }
    write_json(path, manifest)
    return manifest


def _path_value(value: Path | list[Path]) -> str | list[str]:
    if isinstance(value, list):
        return [str(path) for path in value]
    return str(value)


def _hash_inputs(value: Path | list[Path]) -> dict[str, dict[str, int | str]]:
    roots = value if isinstance(value, list) else [value]
    hashes = {}
    for root in roots:
        if root.is_file():
            hashes[str(root)] = {"sha256": sha256_file(root), "size_bytes": root.stat().st_size}
            continue
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            hashes[str(path)] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    return hashes


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"
