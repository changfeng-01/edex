from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferGateInput:
    domain_distance: float
    feature_ood_score: float
    predictive_std: float
    effective_source_samples: float
    physics_coverage: float


@dataclass(frozen=True)
class TransferGateDecision:
    allowed: bool
    trust_score: float
    reasons: tuple[str, ...]
    action: str
