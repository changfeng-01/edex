from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.domain import CircuitDomain, domain_distance, source_domain_weights

from .contracts import TransferGateDecision, TransferGateInput
from .trust import evaluate_transfer_gate


@dataclass(frozen=True)
class TransferAssessment:
    source_weights: dict[str, float]
    weighted_domain_distance: float
    feature_ood_score: float
    effective_source_samples: float
    gate: TransferGateDecision


class CrossCircuitTransferEngine:
    """Coordinate source selection, support diagnostics, and fail-closed gating."""

    def __init__(
        self,
        source_domains: Mapping[str, CircuitDomain],
        target_domain: CircuitDomain,
        *,
        source_temperature: float = 0.25,
        gate_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.source_domains = dict(source_domains)
        self.target_domain = target_domain
        self.source_weights = source_domain_weights(
            self.source_domains, self.target_domain, temperature=source_temperature
        )
        self.gate_config = dict(gate_config or {})

    def assess(
        self,
        history: pd.DataFrame,
        target_state: Mapping[str, float],
        *,
        feature_columns: Sequence[str],
        predictive_std: float,
        physics_coverage: float,
        domain_column: str = "domain_id",
    ) -> TransferAssessment:
        weighted_distance = sum(
            self.source_weights.get(name, 0.0) * domain_distance(domain, self.target_domain).total
            for name, domain in self.source_domains.items()
        )
        per_domain_ood: list[float] = []
        row_weights: list[float] = []
        for name in self.source_domains:
            group = (
                history[history[domain_column].astype(str) == str(name)]
                if domain_column in history
                else history.iloc[0:0]
            )
            if group.empty:
                continue
            feature_scores: list[float] = []
            for feature in feature_columns:
                values = pd.to_numeric(group.get(feature), errors="coerce").dropna()
                target = target_state.get(feature)
                if values.empty or target is None:
                    feature_scores.append(1.0)
                    continue
                median = float(values.median())
                mad = float((values - median).abs().median())
                scale = max(1.4826 * mad, 0.05 * max(abs(median), 1.0), 1.0e-12)
                feature_scores.append(float(np.clip(abs(float(target) - median) / (3.0 * scale), 0.0, 1.0)))
            per_domain_ood.append(max(feature_scores) if feature_scores else 1.0)
            row_weights.extend([self.source_weights.get(name, 0.0) / len(group)] * len(group))
        feature_ood = min(per_domain_ood) if per_domain_ood else 1.0
        weights = np.asarray(row_weights, dtype=float)
        effective_samples = (
            float(weights.sum() ** 2 / np.sum(weights**2)) if weights.size and np.sum(weights**2) > 0 else 0.0
        )
        gate = evaluate_transfer_gate(
            TransferGateInput(
                domain_distance=float(weighted_distance),
                feature_ood_score=float(feature_ood),
                predictive_std=max(float(predictive_std), 0.0),
                effective_source_samples=effective_samples,
                physics_coverage=float(np.clip(physics_coverage, 0.0, 1.0)),
            ),
            self.gate_config,
        )
        return TransferAssessment(
            source_weights=self.source_weights,
            weighted_domain_distance=float(weighted_distance),
            feature_ood_score=float(feature_ood),
            effective_source_samples=effective_samples,
            gate=gate,
        )
