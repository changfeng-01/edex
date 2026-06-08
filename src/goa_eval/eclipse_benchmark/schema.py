from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


PRIMARY_METRICS = [
    "best_feasible_score",
    "normalized_convergence_auc",
    "fe_at_target_score",
    "first_feasible_round",
    "hard_constraint_pass_rate",
    "not_evaluable_rate",
    "candidate_hit_rate",
    "eclipse_benchmark_score",
]

ROLE_NAMES = ["exploitation", "latent_near_l1", "boundary_learning", "diversity"]


@dataclass(frozen=True)
class BenchmarkRun:
    algorithm: str
    seed: str
    run_dir: str
    metrics: dict[str, Any]


class OptimizerAdapter(Protocol):
    name: str

    def initialize(self, initial_samples: Any, param_space: Any, budget: int, seed: int) -> None:
        ...

    def propose(self, history: Any, n_candidates: int) -> Any:
        ...

    def observe(self, evaluated_results: Any) -> None:
        ...
