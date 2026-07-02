from __future__ import annotations

import json

from goa_eval.pia_ca_llso.formal_audit import write_formal_source_lock


def test_formal_source_lock_writes_reproducibility_metadata(tmp_path) -> None:
    history = tmp_path / "history.csv"
    candidates = tmp_path / "candidates.csv"
    history.write_text("candidate_id\nh1\n", encoding="utf-8")
    candidates.write_text("candidate_id\nc1\n", encoding="utf-8")

    write_formal_source_lock(
        tmp_path,
        protocol={"name": "formal"},
        run_summaries=[{"scenario_id": "s1"}],
        scenario_bundles={
            "s1": {
                "history_csv": str(history),
                "candidate_csv": str(candidates),
                "config": {},
                "source_type": "local_fixture",
                "claim_boundary": "CI fixture",
            }
        },
        command_args=["pia-validate", "--smoke"],
    )

    lock = json.loads((tmp_path / "source_lock.json").read_text(encoding="utf-8"))
    assert lock["protocol_hash"]
    assert lock["command_args"] == ["pia-validate", "--smoke"]
    assert lock["engineering_validity"] == "simulation_only"
