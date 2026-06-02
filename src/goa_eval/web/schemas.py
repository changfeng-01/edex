from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


DATA_SOURCE = "real_simulation_csv"
ENGINEERING_VALIDITY = "simulation_only"
MUST_RESIMULATE = True


def evidence_boundary() -> dict[str, Any]:
    return {
        "data_source": DATA_SOURCE,
        "engineering_validity": ENGINEERING_VALIDITY,
        "must_resimulate": MUST_RESIMULATE,
    }


class WebApiSettings(BaseModel):
    web_cases_root: Path = Field(default=Path("outputs/web_cases"))
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    @classmethod
    def from_env(cls) -> "WebApiSettings":
        root = Path(os.getenv("CIRCUITPILOT_WEB_CASES_ROOT", "outputs/web_cases"))
        origins = [
            origin.strip()
            for origin in os.getenv(
                "CIRCUITPILOT_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
        return cls(web_cases_root=root, cors_origins=origins)


class UploadedCaseConfig(BaseModel):
    case_id: str
    circuit_profile: str | None = None
    topology: str | None = None
    stage_count: int | None = None
    output_node_pattern: str = "o{index}"
    generate_candidates: bool = True
    run_llm_analysis: bool = False


class CaseRunResult(BaseModel):
    case_id: str
    status: str
    case_dir: str
    input_dir: str
    analysis_dir: str
    product_demo_case_dir: str | None = None
    bundle_url: str | None = None
    error: str | None = None
    evidence_boundary: dict[str, Any] = Field(default_factory=evidence_boundary)

