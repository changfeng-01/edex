from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class WaveformBundle:
    version_name: str
    time: np.ndarray
    signals: dict[str, np.ndarray]
    data_source: str
    engineering_validity: str
    truth_windows: dict[str, tuple[float, float]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
