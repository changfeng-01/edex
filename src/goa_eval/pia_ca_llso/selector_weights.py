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

ACTIVE_UNCERTAINTY_DIVERSITY_WEIGHTS = {
    "base_score": 0.45,
    "uncertainty": 0.25,
    "batch_diversity": 0.20,
    "hard_gate": 0.10,
}

ACTIVE_INFLUENCE_ON_DEMAND_WEIGHTS = {
    "active_base": 0.30,
    "influence_gain": 0.22,
    "constraint_urgency": 0.18,
    "uncertainty": 0.15,
    "transfer_trust": 0.10,
    "batch_diversity": 0.05,
}

LITERATURE_ENSEMBLE_WEIGHTS = {
    "deaoe": 0.22,
    "hrcea": 0.22,
    "aiea": 0.18,
    "cesaea": 0.20,
    "eccoea_asaa": 0.18,
}
