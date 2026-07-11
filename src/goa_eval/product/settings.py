from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProductSettings:
    database_url: str
    artifact_root: Path
    job_execution_enabled: bool

    @classmethod
    def from_env(cls) -> "ProductSettings":
        return cls(
            database_url=os.getenv(
                "CIRCUITPILOT_DATABASE_URL",
                "sqlite:///outputs/product/circuitpilot.db",
            ),
            artifact_root=Path(
                os.getenv(
                    "CIRCUITPILOT_ARTIFACT_ROOT",
                    "outputs/product/artifacts",
                )
            ),
            job_execution_enabled=os.getenv(
                "CIRCUITPILOT_JOB_EXECUTION_ENABLED",
                "false",
            ).lower()
            in {"1", "true", "yes"},
        )
