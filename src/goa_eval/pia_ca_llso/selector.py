from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from goa_eval.pia_ca_llso.acquisition import attach_acquisition_scores, compute_diversity, explain_acquisition
from goa_eval.pia_ca_llso.leakage import FORMAL_RESULT_LEAKAGE_COLUMNS
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
from goa_eval.pia_ca_llso.value_coercion import strict_bool
from goa_eval.pia_ca_llso.selector_weights import (
    ACTIVE_INFLUENCE_ON_DEMAND_WEIGHTS,
    ACTIVE_UNCERTAINTY_DIVERSITY_WEIGHTS,
    CAPM_ACQUISITION_WEIGHTS,
    CLASSIFIER_HYBRID_WEIGHTS,
    LITERATURE_ENSEMBLE_WEIGHTS,
)


ROLES = ["exploitation_best", "l1_center", "boundary_learning", "diversity_exploration"]

LITERATURE_ENSEMBLE_STRATEGIES = {
    "literature_ensemble_hybrid",
    "deaoe_hrcea_aiea_cesaea_eccoea_asaa",
}

ACTIVE_ACQUISITION_STRATEGY = "active_uncertainty_diversity"
ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY = "active_influence_on_demand"

CLASSIFIER_REQUIRED_STRATEGIES = {
    "classifier_level_hybrid",
    ACTIVE_ACQUISITION_STRATEGY,
    ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY,
    *LITERATURE_ENSEMBLE_STRATEGIES,
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
    elif strategy == "sklearn_surrogate_baseline":
        scored = select_sklearn_surrogate_baseline(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy == "classifier_level_hybrid":
        scored = select_classifier_level_hybrid(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy == ACTIVE_ACQUISITION_STRATEGY:
        scored = select_active_uncertainty_diversity(candidates, history, top_k, config=config)
        selected = scored.head(top_k)
    elif strategy == ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY:
        scored = select_active_influence_on_demand(candidates, history, top_k, config=config)
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
    if strategy in {"classifier_level_hybrid", ACTIVE_ACQUISITION_STRATEGY, ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY}:
        model_report["classifier_model_status"] = _model_status(scored)
    if strategy == ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY:
        model_report["active_lineage"] = [
            "active_uncertainty_diversity:base active acquisition",
            "AIEA-inspired:CAPM-neighborhood influence gain",
            "DEAOE/HRCEA-inspired:on-demand constraint urgency",
            "distributed surrogate ensemble-inspired:transfer trust",
        ]
    if strategy == "sklearn_surrogate_baseline":
        model_report["surrogate_model_status"] = _model_status(scored)
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


def select_sklearn_surrogate_baseline(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    safe_candidates = _drop_result_columns(candidates)
    feature_cols = _shared_numeric_columns(safe_candidates, history)
    output = predict_candidates(train_baseline_models(history, feature_cols), safe_candidates, feature_cols)
    output = _attach_diversity(output, feature_cols)
    output["surrogate_score_component"] = _bounded_series(output["predicted_score"], default=50.0)
    output["surrogate_hard_component"] = _bounded_series(output["p_hard_pass"], default=0.5)
    output["surrogate_uncertainty_component"] = _bounded_series(output["uncertainty"], default=0.5)
    output["acquisition_score"] = (
        0.45 * output["surrogate_score_component"]
        + 0.25 * output["surrogate_hard_component"]
        + 0.20 * output["surrogate_uncertainty_component"]
        + 0.10 * output["diversity_score"].astype(float)
    ).clip(0.0, 1.0)
    output["diagnostic_status"] = "sklearn_surrogate_baseline"
    output["data_source"] = "real_simulation_csv"
    output["engineering_validity"] = "simulation_only"
    output["must_resimulate"] = True
    return output.sort_values(["acquisition_score", "candidate_id"], ascending=[False, True]).head(top_k)


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


def select_active_uncertainty_diversity(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    active_cfg = _nested_config(config, ACTIVE_ACQUISITION_STRATEGY)
    classifier_enabled = _nested_config(config, "classifier_level_hybrid").get("enabled", True) is not False
    candidate_count = max(len(candidates), top_k)
    if classifier_enabled:
        scored = select_classifier_level_hybrid(
            candidates,
            history,
            top_k=candidate_count,
            config=config,
        ).copy()
    else:
        scored = select_capm_distance(
            candidates,
            history,
            top_k=candidate_count,
            config=config,
            diagnostic_status="active_uncertainty_diversity_classifier_disabled",
            sort_by_acquisition=True,
        ).copy()
        scored["classifier_hybrid_score"] = scored["acquisition_score"]
        scored["p_l1"] = 0.5
        scored["p_hard_pass"] = scored["capm_hard_risk_passed"].astype(float)
        scored["predicted_score"] = 50.0
        scored["predicted_level"] = "L2"
        scored["uncertainty"] = 0.5
        scored["level_entropy_uncertainty"] = 0.5
        scored["hard_pass_entropy_uncertainty"] = 0.5
        scored["predicted_score_tree_std"] = 0.0
        scored["score_tree_std_uncertainty"] = 0.5
        scored["model_status"] = "classifier_disabled"

    if scored.empty:
        return scored

    weights = _active_acquisition_weights(active_cfg)
    feature_cols = _shared_numeric_columns(scored, history)

    def _capm_distance_fn(a: pd.Series, b: pd.Series) -> float:
        result = compute_capm_distance(a, b, config=config)
        return float(result.get("distance", float("inf")))

    scored["active_uncertainty_score"] = _bounded_series(
        scored.get("uncertainty", pd.Series(0.5, index=scored.index)),
        default=0.5,
    )
    scored["batch_diversity_score"] = 0.0
    scored["selection_step"] = pd.NA
    scored["active_acquisition_score"] = 0.0
    scored["active_components_json"] = ""

    remaining = scored.copy()
    selected_rows: list[pd.Series] = []
    selected_frame = pd.DataFrame()
    selected_count = min(top_k, len(remaining))

    for step in range(selected_count):
        step_rows = []
        for idx, row in remaining.iterrows():
            if step == 0:
                diversity = 1.0
            else:
                distances = []
                for _, chosen in selected_frame.iterrows():
                    if feature_cols:
                        distances.append(_capm_distance_fn(row, chosen))
                diversity = float(min(distances)) if distances else 1.0
                diversity = float(min(max(diversity, 0.0), 1.0))
            base_score = _bounded(row.get("classifier_hybrid_score", row.get("acquisition_score", 0.0)))
            uncertainty = _bounded(row.get("active_uncertainty_score", 0.5), default=0.5)
            hard_gate = 1.0 if bool(row.get("capm_hard_risk_passed", False)) else 0.0
            active_score = (
                weights["base_score"] * base_score
                + weights["uncertainty"] * uncertainty
                + weights["batch_diversity"] * diversity
                + weights["hard_gate"] * hard_gate
            )
            first_step_score = 0.65 * base_score + 0.25 * uncertainty + 0.10 * hard_gate
            step_rows.append(
                {
                    "index": idx,
                    "active_score": float(min(max(active_score, 0.0), 1.0)),
                    "first_step_score": float(min(max(first_step_score, 0.0), 1.0)),
                    "batch_diversity": diversity,
                    "candidate_id": str(row.get("candidate_id", "")),
                }
            )
        step_frame = pd.DataFrame(step_rows)
        sort_score = "first_step_score" if step == 0 else "active_score"
        winner_index = step_frame.sort_values([sort_score, "candidate_id"], ascending=[False, True]).iloc[0]["index"]
        winner = remaining.loc[winner_index].copy()
        winning_metrics = step_frame[step_frame["index"] == winner_index].iloc[0]
        winner["active_acquisition_score"] = float(winning_metrics["active_score"])
        winner["batch_diversity_score"] = float(winning_metrics["batch_diversity"])
        winner["selection_step"] = step + 1
        winner["active_components_json"] = _active_components_json(winner, weights)
        selected_rows.append(winner)
        selected_frame = pd.concat([selected_frame, winner.to_frame().T], ignore_index=True)
        remaining = remaining.drop(index=winner_index)

    selected = pd.DataFrame(selected_rows)
    if not selected.empty:
        selected["acquisition_score"] = selected["active_acquisition_score"]
        selected["diagnostic_status"] = "active_uncertainty_diversity"

    if not remaining.empty:
        final_selected = selected if not selected.empty else pd.DataFrame()
        for idx, row in remaining.iterrows():
            if final_selected.empty or not feature_cols:
                diversity = 1.0
            else:
                diversity = min(_capm_distance_fn(row, chosen) for _, chosen in final_selected.iterrows())
                diversity = float(min(max(diversity, 0.0), 1.0))
            base_score = _bounded(row.get("classifier_hybrid_score", row.get("acquisition_score", 0.0)))
            uncertainty = _bounded(row.get("active_uncertainty_score", 0.5), default=0.5)
            hard_gate = 1.0 if bool(row.get("capm_hard_risk_passed", False)) else 0.0
            active_score = (
                weights["base_score"] * base_score
                + weights["uncertainty"] * uncertainty
                + weights["batch_diversity"] * diversity
                + weights["hard_gate"] * hard_gate
            )
            remaining.loc[idx, "batch_diversity_score"] = diversity
            remaining.loc[idx, "active_acquisition_score"] = float(min(max(active_score, 0.0), 1.0))
            remaining.loc[idx, "active_components_json"] = _active_components_json(remaining.loc[idx], weights)
        remaining["acquisition_score"] = remaining["active_acquisition_score"]
        remaining["diagnostic_status"] = "active_uncertainty_diversity_unselected"

    ordered = pd.concat([selected, remaining], ignore_index=True, sort=False)
    return ordered.sort_values(
        ["selection_step", "active_acquisition_score", "candidate_id"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)


def select_active_influence_on_demand(
    candidates: pd.DataFrame,
    history: pd.DataFrame,
    top_k: int = 4,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Active acquisition with CAPM-neighborhood influence and on-demand constraint urgency."""
    candidate_count = max(len(candidates), top_k)
    scored = select_active_uncertainty_diversity(candidates, history, candidate_count, config=config).copy()
    if scored.empty:
        return scored

    aiod_cfg = _nested_config(config, ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY)
    weights = _active_influence_on_demand_weights(aiod_cfg)
    feature_cols = _shared_numeric_columns(scored, history)

    influence_enabled = aiod_cfg.get("influence_graph_enabled", True) is not False
    constraint_enabled = aiod_cfg.get("on_demand_constraint_enabled", True) is not False
    transfer_enabled = aiod_cfg.get("transfer_trust_enabled", True) is not False

    scored["influence_gain_score"] = (
        _influence_gain_scores(scored, history, feature_cols, config=config)
        if influence_enabled
        else pd.Series(0.0, index=scored.index, dtype="float64")
    )
    scored["constraint_urgency_score"] = (
        _constraint_urgency_scores(scored)
        if constraint_enabled
        else pd.Series(0.0, index=scored.index, dtype="float64")
    )
    scored["transfer_trust_score"] = (
        _transfer_trust_scores(scored, history, feature_cols)
        if transfer_enabled
        else pd.Series(0.0, index=scored.index, dtype="float64")
    )
    scored["on_demand_eval_priority"] = (
        0.60 * scored["constraint_urgency_score"].astype(float)
        + 0.25 * scored["influence_gain_score"].astype(float)
        + 0.15 * _bounded_series(scored.get("active_uncertainty_score", pd.Series(0.5, index=scored.index)), default=0.5)
    ).clip(0.0, 1.0)
    scored["selection_step"] = pd.NA
    scored["active_influence_on_demand_score"] = 0.0
    scored["aiod_components_json"] = ""
    scored["data_source"] = "real_simulation_csv"
    scored["engineering_validity"] = "simulation_only"
    scored["must_resimulate"] = True

    def _capm_distance_fn(a: pd.Series, b: pd.Series) -> float:
        result = compute_capm_distance(a, b, config=config)
        return float(result.get("distance", float("inf")))

    remaining = scored.copy()
    selected_rows: list[pd.Series] = []
    selected_frame = pd.DataFrame()
    selected_count = min(top_k, len(remaining))

    for step in range(selected_count):
        step_rows = []
        for idx, row in remaining.iterrows():
            diversity = _dynamic_batch_diversity(row, selected_frame, feature_cols, _capm_distance_fn)
            score = _active_influence_on_demand_score(row, diversity, weights)
            step_rows.append(
                {
                    "index": idx,
                    "score": score,
                    "batch_diversity": diversity,
                    "candidate_id": str(row.get("candidate_id", "")),
                }
            )
        step_frame = pd.DataFrame(step_rows)
        winner_index = step_frame.sort_values(["score", "candidate_id"], ascending=[False, True]).iloc[0]["index"]
        winner = remaining.loc[winner_index].copy()
        winning_metrics = step_frame[step_frame["index"] == winner_index].iloc[0]
        winner["batch_diversity_score"] = float(winning_metrics["batch_diversity"])
        winner["active_influence_on_demand_score"] = float(winning_metrics["score"])
        winner["selection_step"] = step + 1
        winner["aiod_components_json"] = _aiod_components_json(winner, weights)
        selected_rows.append(winner)
        selected_frame = pd.concat([selected_frame, winner.to_frame().T], ignore_index=True)
        remaining = remaining.drop(index=winner_index)

    selected = pd.DataFrame(selected_rows)
    if not selected.empty:
        selected["acquisition_score"] = selected["active_influence_on_demand_score"]
        selected["diagnostic_status"] = ACTIVE_INFLUENCE_ON_DEMAND_STRATEGY

    if not remaining.empty:
        final_selected = selected if not selected.empty else pd.DataFrame()
        for idx, row in remaining.iterrows():
            diversity = _dynamic_batch_diversity(row, final_selected, feature_cols, _capm_distance_fn)
            score = _active_influence_on_demand_score(row, diversity, weights)
            remaining.loc[idx, "batch_diversity_score"] = diversity
            remaining.loc[idx, "active_influence_on_demand_score"] = score
            remaining.loc[idx, "aiod_components_json"] = _aiod_components_json(remaining.loc[idx], weights)
        remaining["acquisition_score"] = remaining["active_influence_on_demand_score"]
        remaining["diagnostic_status"] = "active_influence_on_demand_unselected"

    ordered = pd.concat([selected, remaining], ignore_index=True, sort=False)
    return ordered.sort_values(
        ["selection_step", "active_influence_on_demand_score", "candidate_id"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)


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


def _drop_result_columns(frame: pd.DataFrame) -> pd.DataFrame:
    forbidden = set(FORBIDDEN_DISTANCE_COLUMNS) | set(FORMAL_RESULT_LEAKAGE_COLUMNS)
    drop_columns = [column for column in frame.columns if column in forbidden and column != "candidate_id"]
    return frame.drop(columns=drop_columns, errors="ignore")


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
    hard_values = _strict_bool_series(history[hard_col], field=hard_col) if hard_col in history.columns else pd.Series(True, index=history.index)
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
        pass_rate = float(_strict_bool_series(history[hard_col], field=hard_col).mean())
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
    return float(_strict_bool_series(history[hard_col], field=hard_col).mean())


def _strict_bool_series(values: pd.Series, *, field: str) -> pd.Series:
    return values.map(lambda value: strict_bool(value, field=field)).astype(bool)


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


def _influence_gain_scores(
    scored: pd.DataFrame,
    history: pd.DataFrame,
    feature_cols: Sequence[str],
    config: Mapping[str, Any] | None = None,
) -> pd.Series:
    if len(scored) <= 1 or not feature_cols:
        return _influence_fallback_scores(scored)
    k_neighbors = max(1, min(3, len(scored) - 1))
    uncertainty = _bounded_series(scored.get("active_uncertainty_score", pd.Series(0.5, index=scored.index)), default=0.5)
    fallback = _influence_fallback_scores(scored)
    raw_scores: dict[Any, float] = {}
    for idx, row in scored.iterrows():
        neighbors: list[tuple[float, Any]] = []
        for other_idx, other in scored.iterrows():
            if idx == other_idx:
                continue
            try:
                distance = float(compute_capm_distance(row, other, config=config).get("distance", float("inf")))
            except Exception:
                distance = float("inf")
            if pd.isna(distance) or distance == float("inf"):
                continue
            neighbors.append((max(distance, 0.0), other_idx))
        if not neighbors:
            raw_scores[idx] = float(fallback.loc[idx])
            continue
        nearest = sorted(neighbors, key=lambda item: item[0])[:k_neighbors]
        weights = [1.0 / (1.0 + distance) for distance, _ in nearest]
        weighted_uncertainty = sum(weights[pos] * float(uncertainty.loc[other_idx]) for pos, (_, other_idx) in enumerate(nearest))
        total_weight = sum(weights) or 1.0
        neighborhood_need = weighted_uncertainty / total_weight
        density = min(sum(weights) / k_neighbors, 1.0)
        promise = _bounded(row.get("active_acquisition_score", row.get("acquisition_score", 0.5)), default=0.5)
        influence = (0.65 * neighborhood_need + 0.35 * density) * (0.50 + 0.50 * promise)
        raw_scores[idx] = float(min(max(influence, 0.0), 1.0))
    return pd.Series(raw_scores, index=scored.index, dtype="float64").fillna(0.5).clip(0.0, 1.0)


def _influence_fallback_scores(scored: pd.DataFrame) -> pd.Series:
    diversity = _bounded_series(scored.get("diversity_score", pd.Series(0.5, index=scored.index)), default=0.5)
    proximity = 1.0 - _bounded_series(
        scored.get("capm_distance_to_l1_normalized", pd.Series(0.5, index=scored.index)),
        default=0.5,
    )
    return (0.50 * diversity + 0.50 * proximity).clip(0.0, 1.0)


def _constraint_urgency_scores(scored: pd.DataFrame) -> pd.Series:
    p_hard = _bounded_series(scored.get("p_hard_pass", pd.Series(0.5, index=scored.index)), default=0.5)
    boundary_focus = (1.0 - (p_hard - 0.5).abs() * 2.0).clip(0.0, 1.0)
    barrier = _normalized_positive_series(scored.get("capm_barrier_score", pd.Series(0.0, index=scored.index)))
    uncertainty = _bounded_series(scored.get("active_uncertainty_score", pd.Series(0.5, index=scored.index)), default=0.5)
    hard_risk = 1.0 - scored.get("capm_hard_risk_passed", pd.Series(False, index=scored.index)).astype(bool).astype(float)
    return (0.40 * boundary_focus + 0.25 * barrier + 0.25 * uncertainty + 0.10 * hard_risk).clip(0.0, 1.0)


def _transfer_trust_scores(scored: pd.DataFrame, history: pd.DataFrame, feature_cols: Sequence[str]) -> pd.Series:
    if history.empty or not feature_cols:
        return pd.Series(0.5, index=scored.index, dtype="float64")
    pass_rate = _history_pass_rate(history)
    heterogeneity = _feature_heterogeneity(history, feature_cols)
    global_trust = min(max(0.50 + 0.25 * pass_rate + 0.25 * (1.0 - heterogeneity), 0.0), 1.0)
    sample_confidence = 1.0 - _bounded_series(
        scored.get("active_uncertainty_score", pd.Series(0.5, index=scored.index)),
        default=0.5,
    )
    return (0.65 * global_trust + 0.35 * sample_confidence).clip(0.0, 1.0)


def _dynamic_batch_diversity(
    row: pd.Series,
    selected_frame: pd.DataFrame,
    feature_cols: Sequence[str],
    distance_fn: Callable[[pd.Series, pd.Series], float],
) -> float:
    if selected_frame.empty or not feature_cols:
        return 1.0
    distances = [distance_fn(row, chosen) for _, chosen in selected_frame.iterrows()]
    finite = [distance for distance in distances if not pd.isna(distance) and distance != float("inf")]
    if not finite:
        return 1.0
    return float(min(max(min(finite), 0.0), 1.0))


def _active_influence_on_demand_score(row: Mapping[str, Any], batch_diversity: float, weights: Mapping[str, float]) -> float:
    score = (
        weights["active_base"] * _bounded(row.get("active_acquisition_score", row.get("acquisition_score", 0.0)))
        + weights["influence_gain"] * _bounded(row.get("influence_gain_score", 0.5), default=0.5)
        + weights["constraint_urgency"] * _bounded(row.get("constraint_urgency_score", 0.5), default=0.5)
        + weights["uncertainty"] * _bounded(row.get("active_uncertainty_score", row.get("uncertainty", 0.5)), default=0.5)
        + weights["transfer_trust"] * _bounded(row.get("transfer_trust_score", 0.5), default=0.5)
        + weights["batch_diversity"] * _bounded(batch_diversity)
    )
    return float(min(max(score, 0.0), 1.0))


def _normalize_acquisition_weights(weights: Mapping[str, float]) -> dict[str, float]:
    active = {key: float(weights.get(key, CAPM_ACQUISITION_WEIGHTS[key])) for key in CAPM_ACQUISITION_WEIGHTS}
    total = sum(active.values()) or 1.0
    return {key: value / total for key, value in active.items()}


def _active_acquisition_weights(config: Mapping[str, Any]) -> dict[str, float]:
    configured = config.get("weights", {}) if isinstance(config.get("weights", {}), Mapping) else {}
    weights = {
        key: float(configured.get(key, ACTIVE_UNCERTAINTY_DIVERSITY_WEIGHTS[key]))
        for key in ACTIVE_UNCERTAINTY_DIVERSITY_WEIGHTS
    }
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _active_influence_on_demand_weights(config: Mapping[str, Any]) -> dict[str, float]:
    configured = config.get("weights", {}) if isinstance(config.get("weights", {}), Mapping) else {}
    weights = {
        key: float(configured.get(key, ACTIVE_INFLUENCE_ON_DEMAND_WEIGHTS[key]))
        for key in ACTIVE_INFLUENCE_ON_DEMAND_WEIGHTS
    }
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def _active_components_json(row: Mapping[str, Any], weights: Mapping[str, float]) -> str:
    payload = {
        "base_score": _bounded(row.get("classifier_hybrid_score", row.get("acquisition_score", 0.0))),
        "uncertainty": _bounded(row.get("active_uncertainty_score", 0.5), default=0.5),
        "batch_diversity": _bounded(row.get("batch_diversity_score", 0.0)),
        "hard_gate": bool(row.get("capm_hard_risk_passed", False)),
        "level_entropy_uncertainty": _bounded(row.get("level_entropy_uncertainty", 0.5), default=0.5),
        "hard_pass_entropy_uncertainty": _bounded(row.get("hard_pass_entropy_uncertainty", 0.5), default=0.5),
        "predicted_score_tree_std": float(row.get("predicted_score_tree_std", 0.0) or 0.0),
        "score_tree_std_uncertainty": _bounded(row.get("score_tree_std_uncertainty", 0.5), default=0.5),
        "weights": dict(weights),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _aiod_components_json(row: Mapping[str, Any], weights: Mapping[str, float]) -> str:
    payload = {
        "active_base": _bounded(row.get("active_acquisition_score", row.get("acquisition_score", 0.0))),
        "influence_gain": _bounded(row.get("influence_gain_score", 0.5), default=0.5),
        "constraint_urgency": _bounded(row.get("constraint_urgency_score", 0.5), default=0.5),
        "uncertainty": _bounded(row.get("active_uncertainty_score", row.get("uncertainty", 0.5)), default=0.5),
        "transfer_trust": _bounded(row.get("transfer_trust_score", 0.5), default=0.5),
        "batch_diversity": _bounded(row.get("batch_diversity_score", 0.0)),
        "on_demand_eval_priority": _bounded(row.get("on_demand_eval_priority", 0.0)),
        "weights": dict(weights),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _nested_config(config: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    nested = (config or {}).get(key, {})
    return nested if isinstance(nested, Mapping) else {}
