from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from goa_eval.pareto import DEFAULT_OBJECTIVES
from goa_eval.pia_ca_llso.features import DEFAULT_FORBIDDEN_METRIC_NAMES
from goa_eval.pia_ca_llso.validation_protocol import BOUNDARY


DESIGN_VARIABLE_SYMBOL = "x"
HISTORY_SET_SYMBOL = "D_t"
CANDIDATE_SET_SYMBOL = "C_t"
PHYSICS_FEATURE_SYMBOL = "phi"

PRIMARY_SCORE_COLUMN = "overall_score"
PROFILE_OBJECTIVE_COLUMN = "objective_score"
HARD_CONSTRAINT_COLUMN = "hard_constraint_passed"
ACQUISITION_SCORE_COLUMN = "acquisition_score"
PRIMARY_OUTCOME = "simulations_to_target"
TARGET_SCORE_KEY = "target_score"
CLAIM_BOUNDARY = "next-run simulation suggestions"

LEVEL_DEFINITIONS = {
    "L1": "high-score feasible simulation records",
    "L2": "middle-score feasible simulation records",
    "L3": "weak feasible records or hard-constraint failures retained for boundary learning",
    "L4": "failed, not-evaluable, or predicted-only records",
}

OBJECTIVE_LAYERS = {
    "simulation_score": {
        "symbol": "S(x)",
        "column": PRIMARY_SCORE_COLUMN,
        "meaning": "single-run simulation performance score",
    },
    "profile_objective": {
        "symbol": "J_profile(x)",
        "column": PROFILE_OBJECTIVE_COLUMN,
        "meaning": "profile-weighted score emitted by the scoring layer",
    },
    "hard_constraint": {
        "symbol": "H(x)",
        "column": HARD_CONSTRAINT_COLUMN,
        "meaning": "binary hard-constraint feasibility gate",
    },
    "candidate_acquisition": {
        "symbol": "A(x)",
        "column": ACQUISITION_SCORE_COLUMN,
        "meaning": "next-run simulation priority, not final validation evidence",
    },
    "validation_outcome": {
        "symbol": "tau_T",
        "column": PRIMARY_OUTCOME,
        "meaning": "number of imported simulation results needed to reach the target",
    },
}

FORMULAS = {
    "simulation_evaluation": "F(x) = (m(x), S(x), H(x))",
    "primary_outcome": "tau_T = min { t | t <= B, S(x_t) >= T, H(x_t)=1 }",
    "physics_feature_map": "phi: X -> R^d",
    "capm_tensor": (
        "D_tensor(x,y) = sqrt(sum_k w_k (phi_k(x)-phi_k(y))^2 "
        "+ sum_(a,b) rho_ab (phi_a(x)phi_b(x)-phi_a(y)phi_b(y))^2)"
    ),
    "barrier": "B(phi(x)) = sum_j p_j(phi_j(x); theta_j)",
    "capm_pair": (
        "D_pair(x,y) = D_tensor(x,y) + lambda_barrier * max(B(phi(x)), B(phi(y))) "
        "+ lambda_missing * M(x,y)"
    ),
    "l1_geodesic": "D_geodesic(x,L1) = min_{z in L1} shortest_path_G(x,z)",
    "capm_acquisition": (
        "A_capm(x) = alpha_d (1 - norm(D_geodesic(x,L1))) + alpha_v diversity(x) "
        "+ alpha_h I[B(phi(x))=0] + alpha_m (1 - M(x))"
    ),
    "classifier_hybrid": (
        "A_hybrid(x) = beta_1 p_L1(x) + beta_2 p_hard(x) + beta_3 pred_score(x) "
        "+ beta_4 (1 - norm(D_geodesic)) + beta_5 hard_mask(x) + beta_6 diversity(x)"
    ),
    "active_uncertainty_diversity": (
        "A_active(x) = gamma_1 A_hybrid(x) + gamma_2 uncertainty(x) "
        "+ gamma_3 batch_diversity(x|S_t) + gamma_4 hard_gate(x)"
    ),
    "literature_ensemble": "A_lit(x) = sum_r omega_r A_r(x)",
}


@dataclass(frozen=True)
class MethodDefinition:
    problem_name: str
    design_variable_symbol: str
    history_set_symbol: str
    candidate_set_symbol: str
    physics_feature_symbol: str
    parameter_columns: tuple[str, ...]
    target_score: float | None
    score_column: str
    hard_constraint_column: str
    profile_objective_column: str
    acquisition_score_column: str
    primary_outcome: str
    claim_boundary: str
    boundary: dict[str, Any]
    objective_layers: dict[str, dict[str, str]]
    pareto_objectives: tuple[dict[str, str], ...]
    forbidden_leakage_columns: tuple[str, ...]
    level_definitions: dict[str, str]
    formulas: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_method_definition(config: Mapping[str, Any] | None = None) -> MethodDefinition:
    cfg = config or {}
    parameter_columns = tuple(str(item) for item in cfg.get("parameter_columns", ()))
    target_score = _as_float(cfg.get(TARGET_SCORE_KEY))
    score_column = _score_column(cfg)
    hard_column = _hard_constraint_column(cfg)
    forbidden = _forbidden_leakage_columns(cfg)
    return MethodDefinition(
        problem_name=str(cfg.get("problem_name", "pia_ca_llso")),
        design_variable_symbol=DESIGN_VARIABLE_SYMBOL,
        history_set_symbol=HISTORY_SET_SYMBOL,
        candidate_set_symbol=CANDIDATE_SET_SYMBOL,
        physics_feature_symbol=PHYSICS_FEATURE_SYMBOL,
        parameter_columns=parameter_columns,
        target_score=target_score,
        score_column=score_column,
        hard_constraint_column=hard_column,
        profile_objective_column=PROFILE_OBJECTIVE_COLUMN,
        acquisition_score_column=ACQUISITION_SCORE_COLUMN,
        primary_outcome=PRIMARY_OUTCOME,
        claim_boundary=CLAIM_BOUNDARY,
        boundary=dict(BOUNDARY),
        objective_layers=dict(OBJECTIVE_LAYERS),
        pareto_objectives=tuple(dict(item) for item in DEFAULT_OBJECTIVES),
        forbidden_leakage_columns=forbidden,
        level_definitions=dict(LEVEL_DEFINITIONS),
        formulas=dict(FORMULAS),
    )


def _score_column(config: Mapping[str, Any]) -> str:
    labeling = config.get("labeling", {})
    if isinstance(labeling, Mapping) and labeling.get("score_col"):
        return str(labeling["score_col"])
    score_columns = config.get("score_columns", {})
    if isinstance(score_columns, Mapping) and score_columns.get(PRIMARY_SCORE_COLUMN):
        return str(score_columns[PRIMARY_SCORE_COLUMN])
    return PRIMARY_SCORE_COLUMN


def _hard_constraint_column(config: Mapping[str, Any]) -> str:
    labeling = config.get("labeling", {})
    if isinstance(labeling, Mapping) and labeling.get("hard_pass_col"):
        return str(labeling["hard_pass_col"])
    columns = config.get("hard_constraint_columns", ())
    if isinstance(columns, list) and columns:
        return str(columns[0])
    return HARD_CONSTRAINT_COLUMN


def _forbidden_leakage_columns(config: Mapping[str, Any]) -> tuple[str, ...]:
    configured = config.get("forbidden_leakage_columns", ())
    values = list(configured) if isinstance(configured, list) else []
    if not values:
        values = list(DEFAULT_FORBIDDEN_METRIC_NAMES)
    required = [
        PRIMARY_SCORE_COLUMN,
        HARD_CONSTRAINT_COLUMN,
        PROFILE_OBJECTIVE_COLUMN,
        "waveform_score",
        "delay",
        "power",
    ]
    merged = [str(item) for item in values]
    for item in required:
        if item not in merged:
            merged.append(item)
    return tuple(merged)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
