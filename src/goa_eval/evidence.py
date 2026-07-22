from __future__ import annotations

from pathlib import Path
from typing import Any

from goa_eval.io_utils import write_json


DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"

EVIDENCE_FIELDS = [
    "evidence_level",
    "simulation_backend",
    "mock_used",
    "optimizer_claim_level",
]


def build_evidence_metadata(
    *,
    simulation_backend: str = "external_csv",
    mock_used: bool = False,
    optimizer_claim_level: str = "candidate_generated",
    evidence_level: str | None = None,
) -> dict[str, Any]:
    if evidence_level is None:
        evidence_level = infer_evidence_level(
            simulation_backend=simulation_backend,
            mock_used=mock_used,
            optimizer_claim_level=optimizer_claim_level,
        )
    return {
        "evidence_level": evidence_level,
        "simulation_backend": simulation_backend,
        "mock_used": bool(mock_used),
        "optimizer_claim_level": optimizer_claim_level,
    }


def infer_evidence_level(
    *,
    simulation_backend: str,
    mock_used: bool,
    optimizer_claim_level: str,
) -> str:
    if simulation_backend == "public_demo_csv":
        return "level_0_public_demo_csv"
    return "level_1_external_csv"


def default_external_csv_evidence() -> dict[str, Any]:
    return build_evidence_metadata()


def evidence_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = default_external_csv_evidence()
    for field in EVIDENCE_FIELDS:
        if field in payload:
            metadata[field] = payload[field]
    if metadata["evidence_level"] not in {"level_0_public_demo_csv", "level_1_external_csv"}:
        metadata["evidence_level"] = "level_1_external_csv"
    if metadata["simulation_backend"] not in {
        "external_csv",
        "public_demo_csv",
        "empyrean_exported_files",
    }:
        metadata["simulation_backend"] = "external_csv"
    return metadata


def with_evidence(payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **payload,
        "data_source": payload.get("data_source", DATA_SOURCE),
        "engineering_validity": payload.get("engineering_validity", ENGINEERING_VALIDITY),
        **(metadata or default_external_csv_evidence()),
    }


def write_figure_manifest(
    figure_dir: Path,
    *,
    generated_by: str,
    input_data: list[str],
    data_source: str = DATA_SOURCE,
    engineering_validity: str = ENGINEERING_VALIDITY,
    evidence_level: str = "level_1_external_csv",
) -> dict[str, Any]:
    figures = []
    for path in sorted(figure_dir.glob("*.png")):
        figures.append(
            {
                "figure": path.name,
                "generated_by": generated_by,
                "input_data": input_data,
                "source_type": "matplotlib_local",
                "ai_generated": False,
                "llm_used": False,
                "data_source": data_source,
                "engineering_validity": engineering_validity,
                "evidence_level": evidence_level,
            }
        )
    manifest = {"figures": figures}
    write_json(figure_dir / "figure_manifest.json", manifest)
    return manifest
