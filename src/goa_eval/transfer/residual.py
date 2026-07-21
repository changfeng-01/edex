from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


class HierarchicalPhysicsResidual:
    """Small deterministic multi-domain residual model.

    The physics prediction is the shared slope. Domain and fidelity offsets
    model structured residuals without pretending source observations are
    target-domain truth.
    """

    model_name = "hierarchical_physics_residual_v1"

    def __init__(self, ridge: float = 1.0e-3) -> None:
        self.ridge = max(float(ridge), 0.0)
        self._columns: tuple[str, ...] = ()
        self._coefficient = np.asarray([], dtype=float)
        self._physics_column = "physics_prediction"

    def fit(
        self,
        frame: pd.DataFrame,
        targets: Sequence[float],
        *,
        physics_column: str = "physics_prediction",
        domain_column: str = "domain",
        fidelity_column: str = "fidelity",
        sample_weight: Sequence[float] | None = None,
    ) -> "HierarchicalPhysicsResidual":
        self._physics_column = physics_column
        design = self._design(frame, domain_column, fidelity_column, fit=True)
        y = np.asarray(targets, dtype=float)
        weights = np.asarray(sample_weight if sample_weight is not None else np.ones(len(frame)), dtype=float)
        root_w = np.sqrt(np.clip(weights, 0.0, None))
        weighted_x = design * root_w[:, None]
        weighted_y = y * root_w
        penalty = self.ridge * np.eye(design.shape[1])
        penalty[0, 0] = 0.0
        self._coefficient = np.linalg.pinv(weighted_x.T @ weighted_x + penalty) @ weighted_x.T @ weighted_y
        return self

    def predict(
        self,
        frame: pd.DataFrame,
        *,
        domain_column: str = "domain",
        fidelity_column: str = "fidelity",
    ) -> np.ndarray:
        if self._coefficient.size == 0:
            raise RuntimeError("HierarchicalPhysicsResidual must be fit before predict")
        return self._design(frame, domain_column, fidelity_column, fit=False) @ self._coefficient

    def _design(self, frame: pd.DataFrame, domain_column: str, fidelity_column: str, *, fit: bool) -> np.ndarray:
        categorical = pd.get_dummies(
            frame[[domain_column, fidelity_column]].astype(str),
            columns=[domain_column, fidelity_column],
            dtype=float,
        )
        if fit:
            self._columns = tuple(categorical.columns)
        categorical = categorical.reindex(columns=self._columns, fill_value=0.0)
        physics = pd.to_numeric(frame[self._physics_column], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        return np.column_stack([np.ones(len(frame)), physics, categorical.to_numpy(dtype=float)])


def compute_propensity_weights(
    propensities: Sequence[float],
    *,
    minimum_propensity: float = 0.05,
    max_weight: float = 20.0,
) -> np.ndarray:
    values = np.asarray(propensities, dtype=float)
    denominator = np.maximum(values, max(float(minimum_propensity), 1.0e-12))
    return np.minimum(1.0 / denominator, max(float(max_weight), 1.0))
