"""PIA evolution state schema for tracking generation-level metadata."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class GenerationState:
    """Records metadata for one generation of the closed-loop evolution."""

    generation: int
    history_rows: int
    offspring_rows: int
    selected_rows: int
    imported_result_rows: int
    best_score: float | None = None
    stop_reason: str | None = None
    data_source: str = "real_simulation_csv"
    engineering_validity: str = "simulation_only"
    must_resimulate: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize generation state to a JSONL-safe dictionary."""
        return asdict(self)
