from __future__ import annotations

import random
from typing import Any


class RandomAdapter:
    name = "random"

    def __init__(self) -> None:
        self._rng = random.Random(42)
        self._param_space: dict[str, Any] = {}

    def initialize(self, initial_samples: Any, param_space: Any, budget: int, seed: int) -> None:
        self._rng = random.Random(seed)
        self._param_space = dict(param_space or {})

    def propose(self, history: Any, n_candidates: int) -> list[dict[str, Any]]:
        return [_sample(self._param_space, self._rng) for _ in range(max(0, n_candidates))]

    def observe(self, evaluated_results: Any) -> None:
        return None


class ReplayAdapter:
    name = "replay"

    def __init__(self, candidates: list[dict[str, Any]] | None = None) -> None:
        self._candidates = list(candidates or [])

    def initialize(self, initial_samples: Any, param_space: Any, budget: int, seed: int) -> None:
        return None

    def propose(self, history: Any, n_candidates: int) -> list[dict[str, Any]]:
        return self._candidates[: max(0, n_candidates)]

    def observe(self, evaluated_results: Any) -> None:
        return None


def _sample(param_space: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    point: dict[str, Any] = {}
    for name, spec in param_space.items():
        values = spec.get("values") if isinstance(spec, dict) else spec
        if not isinstance(values, list):
            values = [values]
        point[name] = rng.choice(values) if values else None
    return point
