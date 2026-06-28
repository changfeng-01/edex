from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from goa_eval.pia_ca_llso.acquisition import attach_acquisition_scores, compute_diversity, explain_acquisition
from goa_eval.pia_ca_llso.physics_distance import (
    FORBIDDEN_DISTANCE_COLUMNS,
    GOA_DEFAULT_WEIGHTS,
    compute_capm_distance,
    distance_to_l1_physics,
    normalize_distance,
    physics_geodesic_distance_to_l1,
)
from goa_eval.pia_ca_llso.paper_baselines import PAPER_BASELINE_STRATEGIES, select_paper_baseline
from goa_eval.pia_ca_llso.raw_distance import select_by_raw_distance
from goa_eval.pia_ca_llso.schema import SelectionResult
from goa_eval.pia_ca_llso.sklearn_baseline import predict_candidates, train_baseline_models


ROLES = ["exploitation_best", "l1_center", "boundary_learning", "diversity_exploration"]

CAPM_ACQUISITION_WEIGHTS = {
    "distance": 0.45,
    "diversity": 0.25,
    "hard_mask": 0.25,
    "missing_feature_confidence": 0.05,
}

CLASSIFIER_HYBRID_WEIGHTS = {
    "p_l1": 0.30,
    "p_hard_pass": 0.20,
    "predicted_score": 0.20,
    "capm_distance": 0.15,
    "capm_hard_risk_passed": 0.10,
    "diversity_score": 0.05,
}

LITERATURE_ENSEMBLE_STRATEGIES = {
    "literature_ensemble_hybrid",
    "deaoe_hrcea_aiea_cesaea_eccoea_asaa",
}

CLASSIFIER_REQUIRED_STRATEGIES = {"classifier_level_hybrid", *LITERATURE_ENSEMBLE_STRATEGIES}

LITERATURE_ENSEMBLE_WEIGHTS = {
    "deaoe": 0.22,
    "hrcea": 0.22,
    "aiea": 0.18,
    "cesaea": 0.20,
    "eccoea_asaa": 0.18,
}


def select_candidates(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    strategy: str = "pia_physics_distance",
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> SelectionResult:
    if strategy == "random":
        selected = select_random(candidates, top_k)
        scored = selected.copy()
    elif strategy == "ca_llso_raw_distance":
        scored = select_raw_distance(candidates, history, top_k)
        selected = scored.head(top_k)
    elif strategy in {"pia_physics_distance", "pia_latent_metric", "pia_full_attention"}:
        scored = select_physics_distance(candidates, history, top_k)
        selected = scored.head(top_k)
    elif strategy == "pia_capm_distance":
        scored = select_capm_distance(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy == "adaptive_pia_capm":
        scored = select_adaptive_capm_distance(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy == "classifier_level_hybrid":
        scored = select_classifier_level_hybrid(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy in LITERATURE_ENSEMBLE_STRATEGIES:
        scored = select_literature_ensemble_hybrid(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy in PAPER_BASELINE_STRATEGIES:
        scored = select_paper_baseline(candidates, history, strategy=strategy, top_k=top_k, config=config)
        selected = scored.head(top_k)
    else:
        raise ValueError(f"Unknown PIA selection strategy: {strategy}")
    selected = assign_candidate_roles(selected.reset_index(drop=True))
    selected["selection_reason"] = [explain_acquisition(row) for row in selected.to_dict("records")]
    model_report: dict[str, object] = {"strategy": strategy, "selected_count": int(len(selected))}
    if strategy == "classifier_level_hybrid":
        model_report["classifier_model_status"] = _model_status(scored)
    if strategy in LITERATURE_ENSEMBLE_STRATEGIES:
        model_report["classifier_model_status"] = _model_status(scored)
        model_report["paper_lineage"] = [
            "DEAOE:on-demand constraint evaluation",
            "HRCEA:hybrid regressor/classifier feasibility gate",
            "AIEA:influence degree and uncertainty-first scheduling",
            "CESAEA:relaxed classifier ensemble",
            "ECCoEA-ASAA:adaptive surrogate weighting and aggregation",
        ]
    return SelectionResult(
        selected_candidates=selected,
        all_candidates=scored,
        model_report=model_report,
        explanation_report=build_selection_report(selected, strategy),
    )


def select_random(candidates: pd.DataFrame, top_k: int = 4, seed: int = 42) -> pd.DataFrame:
    return candidates.sample(n=min(top_k, len(candidates)), random_state=seed).reset_index(drop=True)


def select_raw_distance(candidates: pd.DataFrame, history: pd.DataFrame, top_k: int = 4) -> pd.DataFrame:
    numeric = [col for col in candidates.columns if col in history.columns and pd.api.types.is_numeric_dtype(candidates[col])]
    selected = select_by_raw_distance(candidates, history, top_k=len(candidates), parameter_names=numeric)
    selected = attach_acquisition_scores(selected)
    return selected.sort_values(["acquisition_score", "raw_distance_to_l1"], ascending=[False, True]).head(top_k)


def select_physics_distance(candidates: pd.DataFrame, history: pd.DataFrame, top_k: int = 4) -> pd.DataFrame:
    output = candidates.copy()
    l1 = history[history.get("level_label", "") == "L1"] if "level_label" in history.columns else pd.DataFrame()
    feature_cols = _shared_numeric_columns(output, history)
    distances = []
    for _, row in output.iterrows():
        result = distance_to_l1_physics(row[feature_cols], l1[feature_cols] if not l1.empty else l1)
        distances.append(result["distance"] if result["distance"] is not None else float("inf"))
    output["physics_distance_to_l1"] = normalize_distance(distances)
    output = _attach_diversity(output, feature_cols)
    output = attach_acquisition_scores(output)
    return output.sort_values("acquisition_score", ascending=False).head(top_k)


def select_capm_distance(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
    weights: Mapping[str, float] | None = None,
    acquisition_weights: Mapping[str, float] | None = None,
    diagnostic_status: str = "capm_physics_manifold_no_training",
    sort_by_acquisition: bool = False,
) -> pd.DataFrame:
    output = candidates.copy()
    feature_cols = _shared_numeric_columns(output, history)
    scored = physics_geodesic_distance_to_l1(
        output[["candidate_id", *feature_cols]] if "candidate_id" in output else output[feature_cols],
        history[feature_cols + _history_label_columns(history)],
        weights=weights,
        config=config,
    )
    for column in ["capm_distance_to_l1", "capm_geodesic_distance_to_l1", "capm_barrier_score", "capm_missing_penalty", "capm_status"]:
        output[column] = scored[column].values
    output["capm_distance_to_l1_normalized"] = normalize_distance(output["capm_geodesic_distance_to_l1"].tolist())
    # Use CAPM distance for diversity to align with physics-manifold semantics
    def _capm_distance_fn(a: pd.Series, b: pd.Series) -> float:
        result = compute_capm_distance(a, b, weights=weights, config=config)
        return float(result.get("distance", float("inf")))

    output = _attach_diversity(output, feature_cols, distance_fn=_capm_distance_fn)
    output["capm_hard_risk_passed"] = pd.Series(
        [bool(value <= 0.0) for value in output["capm_barrier_score"].astype(float)],
        index=output.index,
        dtype="object",
    )
    active_weights = _normalize_acquisition_weights(acquisition_weights or CAPM_ACQUISITION_WEIGHTS)
    output["acquisition_score"] = (
        active_weights["distance"] * (1.0 - output["capm_distance_to_l1_normalized"].astype(float))
        + active_weights["diversity"] * output["diversity_score"].astype(float)
        + active_weights["hard_mask"] * output["capm_hard_risk_passed"].astype(float)
        + active_weights["missing_feature_confidence"] * (1.0 - output["capm_missing_penalty"].astype(float).clip(0.0, 1.0))
    ).clip(0.0, 1.0)
    weights_json = json.dumps(dict(weights or {}), ensure_ascii=False, sort_keys=True)
    acquisition_weights_json = json.dumps(active_weights, ensure_ascii=False, sort_keys=True)
    output["acquisition_components_json"] = [
        json.dumps(
            {
                "distance": float(1.0 - row["capm_distance_to_l1_normalized"]),
                "diversity": float(row["diversity_score"]),
                "hard_mask": bool(row["capm_hard_risk_passed"]),
                "missing_feature_confidence": float(1.0 - min(max(row["capm_missing_penalty"], 0.0), 1.0)),
                "diagnostic_status": diagnostic_status,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for _, row in output.iterrows()
    ]
    output["diagnostic_status"] = diagnostic_status
    if weights is not None:
        output["adaptive_capm_weights_json"] = weights_json
        output["adaptive_acquisition_weights_json"] = acquisition_weights_json
    if sort_by_acquisition:
        return output.sort_values(
            ["acquisition_score", "capm_hard_risk_passed", "capm_distance_to_l1_normalized", "candidate_id"],
            ascending=[False, False, True, True],
        ).head(top_k)
    return output.sort_values(
        ["capm_hard_risk_passed", "capm_distance_to_l1_normalized", "diversity_score", "candidate_id"],
        ascending=[False, True, False, True],
    ).head(top_k)


def select_adaptive_capm_distance(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    feature_cols = _shared_numeric_columns(candidates, history)
    weights = _learn_adaptive_capm_weights(history, feature_cols, config)
    acquisition_weights = _adaptive_acquisition_weights(history, config)
    return select_capm_distance(
        candidates,
        history,
        top_k=top_k,
        config=config,
        weights=weights,
        acquisition_weights=acquisition_weights,
        diagnostic_status="adaptive_capm_from_history",
        sort_by_acquisition=True,
    )


def select_classifier_level_hybrid(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    feature_cols = _shared_numeric_columns(candidates, history)
    output = _ensure_classifier_predictions(candidates, history, feature_cols)
    capm = select_capm_distance(
        output,
        history,
        top_k=max(len(output), top_k),
        config=config,
        diagnostic_status="classifier_level_hybrid",
    ).copy()
    distance_component = 1.0 - capm["capm_distance_to_l1_normalized"].astype(float).clip(0.0, 1.0)
    p_l1 = capm["p_l1"].map(_bounded)
    p_hard = capm["p_hard_pass"].map(_bounded)
    predicted_score = capm["predicted_score"].map(_bounded)
    hard_mask = capm["capm_hard_risk_passed"].astype(float)
    diversity = capm["diversity_score"].map(_bounded)
    capm["classifier_hybrid_score"] = (
        CLASSIFIER_HYBRID_WEIGHTS["p_l1"] * p_l1
        + CLASSIFIER_HYBRID_WEIGHTS["p_hard_pass"] * p_hard
        + CLASSIFIER_HYBRID_WEIGHTS["predicted_score"] * predicted_score
        + CLASSIFIER_HYBRID_WEIGHTS["capm_distance"] * distance_component
        + CLASSIFIER_HYBRID_WEIGHTS["capm_hard_risk_passed"] * hard_mask
        + CLASSIFIER_HYBRID_WEIGHTS["diversity_score"] * diversity
    ).clip(0.0, 1.0)
    capm["acquisition_score"] = capm["classifier_hybrid_score"]
    capm["classifier_components_json"] = [
        json.dumps(
            {
                "p_l1": float(row["p_l1"]),
                "p_hard_pass": float(row["p_hard_pass"]),
                "predicted_score": float(_bounded(row["predicted_score"])),
                "capm_distance": float(1.0 - row["capm_distance_to_l1_normalized"]),
                "capm_hard_risk_passed": bool(row["capm_hard_risk_passed"]),
                "diversity_score": float(row["diversity_score"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for _, row in capm.iterrows()
    ]
    capm["diagnostic_status"] = "classifier_level_hybrid"
    return capm.sort_values(
        ["classifier_hybrid_score", "capm_hard_risk_passed", "p_l1", "candidate_id"],
        ascending=[False, False, False, True],
    ).head(top_k)


def select_literature_ensemble_hybrid(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Paper-inspired ensemble gate for the PIA outer-loop skeleton.

    The columns deliberately expose each paper influence so reports can audit
    why a candidate was scheduled for simulation.
    """
    feature_cols = _shared_numeric_columns(candidates, history)
    predicted = _ensure_classifier_predictions(candidates, history, feature_cols)
    capm = select_capm_distance(
        predicted,
        history,
        top_k=max(len(predicted), top_k),
        config=config,
        diagnostic_status="literature_ensemble_hybrid",
    ).copy()
    p_l1 = _bounded_series(capm.get("p_l1", pd.Series(0.0, index=capm.index)))
    p_hard = _bounded_series(capm.get("p_hard_pass", pd.Series(0.0, index=capm.index)))
    predicted_score = _bounded_series(capm.get("predicted_score", pd.Series(0.0, index=capm.index)))
    uncertainty = _bounded_series(capm.get("uncertainty", pd.Series(0.5, index=capm.index)), default=0.5)
    distance = 1.0 - _bounded_series(capm["capm_distance_to_l1_normalized"])
    diversity = _bounded_series(capm["diversity_score"])
    hard_mask = capm["capm_hard_risk_passed"].astype(float).clip(0.0, 1.0)
    barrier_pressure = _normalized_positive_series(capm.get("capm_barrier_score", pd.Series(0.0, index=capm.index)))
    best_score = _bounded(history["overall_score"].max()) if "overall_score" in history.columns and not history.empty else 0.0
    predicted_improvement = (predicted_score - best_score).clip(0.0, 1.0)

    literature_cfg = _nested_config(config, "literature_ensemble_hybrid")
    alpha_cut = float(literature_cfg.get("hrcea_alpha_cut", 0.65))
    relaxation_margin = float(literature_cfg.get("cesaea_relaxation_margin", 0.10))

    joint_sample_promise = (
        0.40 * predicted_score
        + 0.25 * p_l1
        + 0.20 * distance
        + 0.15 * diversity
    ).clip(0.0, 1.0)
    capm["deaoe_constraint_urgency"] = (
        0.55 * (1.0 - p_hard)
        + 0.30 * barrier_pressure
        + 0.15 * uncertainty
    ).clip(0.0, 1.0)
    capm["deaoe_on_demand_priority"] = (
        joint_sample_promise * (0.75 + 0.25 * capm["deaoe_constraint_urgency"])
    ).clip(0.0, 1.0)

    boundary_focus = (1.0 - (p_hard - 0.5).abs() * 2.0).clip(0.0, 1.0)
    capm["hrcea_alpha_gate_passed"] = pd.Series(
        [(bool(p >= alpha_cut) or bool(hard)) for p, hard in zip(p_hard, hard_mask.astype(bool))],
        index=capm.index,
        dtype="object",
    )
    capm["hrcea_rectification_score"] = (
        0.42 * p_hard
        + 0.22 * (1.0 - uncertainty)
        + 0.20 * distance
        + 0.16 * boundary_focus
    ).clip(0.0, 1.0)
    capm.loc[~capm["hrcea_alpha_gate_passed"].astype(bool), "hrcea_rectification_score"] *= 0.80

    capm["aiea_uncertainty_need"] = (uncertainty * (0.50 + 0.50 * p_l1)).clip(0.0, 1.0)
    capm["aiea_influence_score"] = (
        0.45 * predicted_improvement
        + 0.30 * diversity
        + 0.15 * distance
        + 0.10 * capm["aiea_uncertainty_need"]
    ).clip(0.0, 1.0)

    classifier_vote = (p_l1 + p_hard + predicted_score) / 3.0
    relaxed_vote = classifier_vote.copy()
    relaxable = (hard_mask.astype(bool)) & (classifier_vote >= max(alpha_cut - relaxation_margin, 0.0))
    relaxed_vote.loc[relaxable] = (relaxed_vote.loc[relaxable] + relaxation_margin).clip(0.0, 1.0)
    capm["cesaea_relaxed_vote_score"] = (
        0.72 * relaxed_vote
        + 0.18 * hard_mask
        + 0.10 * (1.0 - uncertainty)
    ).clip(0.0, 1.0)

    heterogeneity = _feature_heterogeneity(history, feature_cols)
    sample_weight = (0.55 + 0.45 * (1.0 - uncertainty)).clip(0.0, 1.0)
    aggregation_trust = min(max(0.55 + 0.20 * _history_pass_rate(history) + 0.25 * (1.0 - heterogeneity), 0.0), 1.0)
    capm["eccoea_asaa_sample_weight"] = sample_weight
    capm["eccoea_asaa_aggregation_trust"] = aggregation_trust
    capm["eccoea_asaa_weighted_score"] = (
        aggregation_trust
        * sample_weight
        * (0.40 * capm["cesaea_relaxed_vote_score"] + 0.30 * distance + 0.30 * diversity)
    ).clip(0.0, 1.0)

    weights = _literature_ensemble_weights(config)
    capm["literature_ensemble_score"] = (
        weights["deaoe"] * capm["deaoe_on_demand_priority"]
        + weights["hrcea"] * capm["hrcea_rectification_score"]
        + weights["aiea"] * capm["aiea_influence_score"]
        + weights["cesaea"] * capm["cesaea_relaxed_vote_score"]
        + weights["eccoea_asaa"] * capm["eccoea_asaa_weighted_score"]
    ).clip(0.0, 1.0)
    capm["acquisition_score"] = capm["literature_ensemble_score"]
    capm["literature_components_json"] = [
        json.dumps(
            {
                "deaoe_on_demand_priority": float(row["deaoe_on_demand_priority"]),
                "deaoe_constraint_urgency": float(row["deaoe_constraint_urgency"]),
                "hrcea_rectification_score": float(row["hrcea_rectification_score"]),
                "hrcea_alpha_gate_passed": bool(row["hrcea_alpha_gate_passed"]),
                "aiea_influence_score": float(row["aiea_influence_score"]),
                "aiea_uncertainty_need": float(row["aiea_uncertainty_need"]),
                "cesaea_relaxed_vote_score": float(row["cesaea_relaxed_vote_score"]),
                "eccoea_asaa_weighted_score": float(row["eccoea_asaa_weighted_score"]),
                "eccoea_asaa_aggregation_trust": float(row["eccoea_asaa_aggregation_trust"]),
                "weights": weights,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for _, row in capm.iterrows()
    ]
    capm["diagnostic_status"] = "literature_ensemble_hybrid"
    return capm.sort_values(
        ["literature_ensemble_score", "hrcea_alpha_gate_passed", "capm_hard_risk_passed", "candidate_id"],
        ascending=[False, False, False, True],
    ).head(top_k)


def assign_candidate_roles(selected: pd.DataFrame) -> pd.DataFrame:
    output = selected.copy()
    output["selected_rank"] = range(1, len(output) + 1)
    output["candidate_role"] = [ROLES[idx] if idx < len(ROLES) else "additional_candidate" for idx in range(len(output))]
    return output


def build_selection_report(selected: pd.DataFrame, strategy: str = "pia_physics_distance") -> dict[str, object]:
    return {
        "strategy": strategy,
        "selected_count": int(len(selected)),
        "candidate_ids": list(selected.get("candidate_id", pd.Series(dtype="object"))),
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "claim_boundary": "next-run simulation suggestions",
    }


def _ensure_classifier_predictions(candidates: pd.DataFrame, history: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    required = {"p_l1", "predicted_level", "predicted_score", "p_hard_pass", "uncertainty", "model_status"}
    if required.issubset(candidates.columns):
        return candidates.copy()
    models = train_baseline_models(history, feature_cols)
    return predict_candidates(models, candidates, feature_cols)


def _model_status(frame: pd.DataFrame) -> str:
    statuses = {str(value) for value in frame.get("model_status", pd.Series(dtype="object")).dropna().unique()}
    if "ok" in statuses:
        return "ok"
    if statuses:
        return sorted(statuses)[0]
    return "insufficient_data"


def _bounded(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    if numeric > 1.0:
        numeric = numeric / 100.0
    return float(min(max(numeric, 0.0), 1.0))


def _bounded_series(values: pd.Series, default: float = 0.0) -> pd.Series:
    return values.map(lambda value: _bounded(value, default=default)).astype(float)


def _normalized_positive_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    max_value = float(numeric.max()) if not numeric.empty else 0.0
    if max_value <= 0.0:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return (numeric / max_value).clip(0.0, 1.0)


def _shared_numeric_columns(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    return [
        col
        for col in left.columns
        if col in right.columns and col not in FORBIDDEN_DISTANCE_COLUMNS and pd.api.types.is_numeric_dtype(left[col])
    ]


def _history_label_columns(history: pd.DataFrame) -> list[str]:
    return [column for column in ["sample_id", "level_label"] if column in history.columns]


def _attach_diversity(
    frame: pd.DataFrame,
    feature_cols: Sequence[str],
    distance_fn: Callable[[pd.Series, pd.Series], float] | None = None,
) -> pd.DataFrame:
    output = frame.copy()
    selected = pd.DataFrame()
    scores = []
    for _, row in output.iterrows():
        score = compute_diversity(row, selected, feature_cols, distance_fn=distance_fn)
        scores.append(score)
        selected = pd.concat([selected, row.to_frame().T], ignore_index=True)
    output["diversity_score"] = scores
    return output


def _learn_adaptive_capm_weights(
    history: pd.DataFrame,
    feature_cols: Sequence[str],
    config: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    adaptive_config = _nested_config(config, "adaptive_capm")
    min_rows = int(adaptive_config.get("min_history_rows", 4))
    configured = (config or {}).get("feature_weights", {})
    base = {col: float(configured.get(col, GOA_DEFAULT_WEIGHTS.get(col, 1.0))) for col in feature_cols}
    if len(history) < min_rows:
        return base
    hard_col = "hard_constraint_passed" if "hard_constraint_passed" in history.columns else "hard_pass"
    hard_values = history[hard_col].astype(bool) if hard_col in history.columns else pd.Series(True, index=history.index)
    score_values = pd.to_numeric(history.get("overall_score", pd.Series(dtype="float64")), errors="coerce")
    learned: dict[str, float] = {}
    for col in feature_cols:
        values = pd.to_numeric(history[col], errors="coerce")
        finite = values.replace([float("inf"), float("-inf")], pd.NA).dropna()
        if finite.nunique() <= 1:
            learned[col] = base[col]
            continue
        pass_gap = 0.0
        if hard_values.nunique() > 1:
            passed = values[hard_values].dropna()
            failed = values[~hard_values].dropna()
            if not passed.empty and not failed.empty:
                pass_gap = abs(float(passed.mean()) - float(failed.mean())) / max(float(values.std(skipna=True) or 0.0), 1e-9)
        score_corr = 0.0
        if score_values.notna().sum() >= 3:
            corr = values.corr(score_values)
            if pd.notna(corr):
                score_corr = abs(float(corr))
        learned[col] = float(max(base[col] * (1.0 + min(pass_gap, 3.0) + min(score_corr, 1.0)), 0.01))
    return learned


def _adaptive_acquisition_weights(history: pd.DataFrame, config: Mapping[str, Any] | None = None) -> dict[str, float]:
    adaptive_config = _nested_config(config, "adaptive_capm")
    weights = dict(CAPM_ACQUISITION_WEIGHTS)
    hard_col = "hard_constraint_passed" if "hard_constraint_passed" in history.columns else "hard_pass"
    if hard_col in history.columns and not history.empty:
        pass_rate = float(history[hard_col].astype(bool).mean())
        if pass_rate < 0.5:
            weights.update({"distance": 0.35, "diversity": 0.20, "hard_mask": 0.40, "missing_feature_confidence": 0.05})
    if "level_label" in history.columns and int((history["level_label"] == "L1").sum()) >= int(adaptive_config.get("l1_distance_boost_min_count", 2)):
        weights.update({"distance": max(weights["distance"], 0.50), "diversity": 0.20})
    return _normalize_acquisition_weights(weights)


def _literature_ensemble_weights(config: Mapping[str, Any] | None = None) -> dict[str, float]:
    nested = _nested_config(config, "literature_ensemble_hybrid")
    configured = nested.get("weights", {}) if isinstance(nested.get("weights", {}), Mapping) else {}
    weights = {
        key: float(configured.get(key, LITERATURE_ENSEMBLE_WEIGHTS[key]))
        for key in LITERATURE_ENSEMBLE_WEIGHTS
    }
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _history_pass_rate(history: pd.DataFrame) -> float:
    hard_col = "hard_constraint_passed" if "hard_constraint_passed" in history.columns else "hard_pass"
    if hard_col not in history.columns or history.empty:
        return 0.5
    return float(history[hard_col].astype(bool).mean())


def _feature_heterogeneity(history: pd.DataFrame, feature_cols: Sequence[str]) -> float:
    if history.empty or not feature_cols:
        return 0.5
    ratios: list[float] = []
    for col in feature_cols:
        values = pd.to_numeric(history[col], errors="coerce").dropna()
        if len(values) < 2:
            continue
        mean_abs = abs(float(values.mean()))
        std = float(values.std(skipna=True) or 0.0)
        ratios.append(min(std / max(mean_abs, 1e-9), 1.0))
    if not ratios:
        return 0.5
    return float(sum(ratios) / len(ratios))


def _normalize_acquisition_weights(weights: Mapping[str, float]) -> dict[str, float]:
    active = {key: float(weights.get(key, CAPM_ACQUISITION_WEIGHTS[key])) for key in CAPM_ACQUISITION_WEIGHTS}
    total = sum(active.values()) or 1.0
    return {key: value / total for key, value in active.items()}


def _nested_config(config: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    nested = (config or {}).get(key, {})
    return nested if isinstance(nested, Mapping) else {}
