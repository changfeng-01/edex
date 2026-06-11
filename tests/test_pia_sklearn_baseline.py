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
