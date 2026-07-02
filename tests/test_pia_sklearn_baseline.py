from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.sklearn_baseline import predict_candidates, train_baseline_models


def test_sklearn_baseline_returns_safe_fallback_for_insufficient_data() -> None:
    history = pd.DataFrame([{"f1": 1.0, "level_label": "L1", "hard_pass": True, "overall_score": 90.0}])
    candidates = pd.DataFrame([{"candidate_id": "c1", "f1": 2.0}])

    models = train_baseline_models(history, ["f1"])
    predicted = predict_candidates(models, candidates, ["f1"])

    assert predicted.loc[0, "model_status"] == "insufficient_data"
    assert 0 <= predicted.loc[0, "p_l1"] <= 1
    assert predicted.loc[0, "uncertainty"] == 0.5


def test_sklearn_baseline_exposes_forest_uncertainty_components() -> None:
    history = pd.DataFrame([
        {"f1": 1.0, "f2": 0.0, "level_label": "L1", "hard_pass": True, "overall_score": 95.0},
        {"f1": 1.2, "f2": 0.1, "level_label": "L1", "hard_pass": True, "overall_score": 90.0},
        {"f1": 2.0, "f2": 1.0, "level_label": "L2", "hard_pass": True, "overall_score": 75.0},
        {"f1": 2.2, "f2": 1.2, "level_label": "L2", "hard_pass": True, "overall_score": 70.0},
        {"f1": 3.0, "f2": 2.0, "level_label": "L4", "hard_pass": False, "overall_score": 25.0},
        {"f1": 3.2, "f2": 2.2, "level_label": "L4", "hard_pass": False, "overall_score": 20.0},
    ])
    candidates = pd.DataFrame([
        {"candidate_id": "c1", "f1": 1.1, "f2": 0.1},
        {"candidate_id": "c2", "f1": 2.6, "f2": 1.6},
    ])

    models = train_baseline_models(history, ["f1", "f2"])
    predicted = predict_candidates(models, candidates, ["f1", "f2"])

    assert predicted["model_status"].eq("ok").all()
    for column in [
        "level_entropy_uncertainty",
        "hard_pass_entropy_uncertainty",
        "predicted_score_tree_std",
        "score_tree_std_uncertainty",
        "uncertainty",
    ]:
        assert column in predicted.columns
    assert predicted["uncertainty"].between(0.0, 1.0).all()
    assert predicted["predicted_score_tree_std"].ge(0.0).all()
