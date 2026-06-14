from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.report import render_candidate_report


def test_candidate_report_includes_must_resimulate_boundary() -> None:
    selected = pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "selected_rank": 1,
                "candidate_role": "exploitation_best",
                "acquisition_score": 0.9,
                "selection_reason": "candidate selection proxy",
            }
        ]
    )

    report = render_candidate_report(selected, {"strategy": "pia_capm_distance"})

    assert "must_resimulate = true" in report
