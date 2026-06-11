from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.constraint_ledger import attach_constraint_ledger


def test_constraint_ledger_marks_failed_constraints_without_dropping_rows() -> None:
    frame = pd.DataFrame([{"sample_id": "s1", "delay": 12.0, "power": 2.0}])

    ledgered = attach_constraint_ledger(
        frame,
        {"constraints": {"delay": {"max": 10.0}, "power": {"max": 5.0}}},
    )

    assert ledgered.loc[0, "constraint_violation"] > 0
    assert "delay" in ledgered.loc[0, "constraint_ledger_json"]
