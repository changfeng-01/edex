from __future__ import annotations

from pathlib import Path
from typing import Any

from goa_eval.empyrean.schemas import EXECUTION_MODE, TOOLCHAIN, base_versions, evidence_boundary
from goa_eval.io_utils import sha256_file, write_json


def write_empyrean_case_manifest(
    path: Path,
    *,
    case_id: str,
    input_dir: Path,
    output_dir: Path,
    artifacts: dict[str, list[Path]],
    normalized_waveform_path: Path | None,
    physical_verification_summary_path: Path,
    parasitic_summary_path: Path,
    model_artifact_summary_path: Path,
    data_source: str,
    interface_manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest = {
        **base_versions(),
        "case_id": case_id,
        "toolchain": TOOLCHAIN,
        "execution_mode": EXECUTION_MODE,
        "tool_invocation": False,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "model_artifacts": _artifact_records(artifacts.get("model", [])),
        "schematic_artifacts": _artifact_records(artifacts.get("schematic", [])),
        "layout_artifacts": _artifact_records(artifacts.get("layout", [])),
        "verification_artifacts": _artifact_records(artifacts.get("verification", [])),
        "rc_artifacts": _artifact_records(artifacts.get("rc", [])),
        "simulation_artifacts": _artifact_records(artifacts.get("simulation", [])),
        "normalized_waveform_path": str(normalized_waveform_path) if normalized_waveform_path else None,
        "physical_verification_summary_path": str(physical_verification_summary_path),
        "parasitic_summary_path": str(parasitic_summary_path),
        "model_artifact_summary_path": str(model_artifact_summary_path),
        "interface_manifest_path": str(interface_manifest_path) if interface_manifest_path else None,
        "evidence_boundary": evidence_boundary(data_source),
    }
    write_json(path, manifest)
    return manifest


def _artifact_records(paths: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        if not path.exists():
            continue
        records.append(
            {
                "path": str(path),
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records
