from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from .contracts import TransferGateDecision, TransferGateInput


def evaluate_transfer_gate(value: TransferGateInput, config: Mapping[str, Any] | None = None) -> TransferGateDecision:
    cfg = dict(config or {})
    reasons: list[str] = []
    if value.domain_distance > float(cfg.get("max_domain_distance", 0.35)):
        reasons.append("domain_distance")
    if value.feature_ood_score > float(cfg.get("max_feature_ood", 0.5)):
        reasons.append("feature_ood")
    if value.predictive_std > float(cfg.get("max_predictive_std", 0.25)):
        reasons.append("predictive_uncertainty")
    if value.effective_source_samples < float(cfg.get("min_effective_samples", 5.0)):
        reasons.append("source_support")
    if value.physics_coverage < float(cfg.get("min_physics_coverage", 0.8)):
        reasons.append("physics_coverage")
    normalized_risks = (
        value.domain_distance / max(float(cfg.get("max_domain_distance", 0.35)), 1.0e-12),
        value.feature_ood_score / max(float(cfg.get("max_feature_ood", 0.5)), 1.0e-12),
        value.predictive_std / max(float(cfg.get("max_predictive_std", 0.25)), 1.0e-12),
        max(float(cfg.get("min_effective_samples", 5.0)) - value.effective_source_samples, 0.0)
        / max(float(cfg.get("min_effective_samples", 5.0)), 1.0e-12),
        max(float(cfg.get("min_physics_coverage", 0.8)) - value.physics_coverage, 0.0)
        / max(float(cfg.get("min_physics_coverage", 0.8)), 1.0e-12),
    )
    trust = float(np.clip(1.0 - np.mean(np.clip(normalized_risks, 0.0, 1.0)), 0.0, 1.0))
    return TransferGateDecision(
        allowed=not reasons,
        trust_score=trust,
        reasons=tuple(reasons),
        action="transfer_enabled" if not reasons else "target_only_exploration",
    )
