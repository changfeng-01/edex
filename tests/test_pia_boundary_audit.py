from __future__ import annotations

import pandas as pd

from goa_eval.pia_ca_llso.boundary_audit import audit_evolution_outputs


def test_boundary_audit_passes_valid_evolution_outputs(tmp_path) -> None:
    gen_dir = tmp_path / "generation_000"
    gen_dir.mkdir()
    pd.DataFrame([
        {
            "candidate_id": "c0",
            "must_resimulate": True,
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        },
    ]).to_csv(gen_dir / "simulation_batch.csv", index=False)
    pd.DataFrame([
        {
            "candidate_id": "c0",
            "source": "simulation_result",
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": False,
        },
    ]).to_csv(gen_dir / "imported_results.csv", index=False)
    (tmp_path / "evolution_report.md").write_text(
        "These results are simulation-only and do not constitute physical validation.",
        encoding="utf-8",
    )

    report = audit_evolution_outputs(tmp_path)

    assert report["passed"] is True
    assert report["issues"] == []


def test_boundary_audit_flags_missing_and_overclaiming_fields(tmp_path) -> None:
    gen_dir = tmp_path / "generation_000"
    gen_dir.mkdir()
    pd.DataFrame([
        {"candidate_id": "c0", "must_resimulate": False},
    ]).to_csv(gen_dir / "simulation_batch.csv", index=False)
    pd.DataFrame([
        {
            "candidate_id": "c0",
            "source": "simulation_result",
            "data_source": "paper_reference",
            "engineering_validity": "physical_validated",
        },
    ]).to_csv(gen_dir / "imported_results.csv", index=False)
    (tmp_path / "evolution_report.md").write_text(
        "This run achieved silicon validation complete.",
        encoding="utf-8",
    )

    report = audit_evolution_outputs(tmp_path)

    assert report["passed"] is False
    issue_text = "\n".join(issue["message"] for issue in report["issues"])
    assert "engineering_validity" in issue_text
    assert "must_resimulate" in issue_text
    assert "data_source" in issue_text
    assert "overclaim" in issue_text
