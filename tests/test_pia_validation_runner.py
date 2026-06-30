from __future__ import annotations

import json

from goa_eval.pia_ca_llso.scenario_registry import load_scenario
from goa_eval.pia_ca_llso.validation_protocol import ValidationRunSpec
from goa_eval.pia_ca_llso.validation_runner import run_validation_spec


def _spec() -> ValidationRunSpec:
    return ValidationRunSpec(
        scenario_id="sample_goa",
        method="pia_evolve_full",
        ablation="full",
        seed=11,
        budget=8,
        target_score=80,
    )


def test_validation_runner_executes_single_local_fixture_run(tmp_path) -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")

    summary = run_validation_spec(_spec(), bundle, tmp_path, smoke=True)

    assert summary["scenario_id"] == "sample_goa"
    assert summary["simulations_used"] <= 8
    assert summary["engineering_validity"] == "simulation_only"


def test_validation_runner_writes_run_manifest_and_summary(tmp_path) -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")

    summary = run_validation_spec(_spec(), bundle, tmp_path, smoke=True)
    run_dir = tmp_path / summary["run_path"]

    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "run_summary.json").exists()
    assert (run_dir / "best_so_far_curve.csv").exists()
    assert summary["result_source"] == "best_so_far_curve.csv"
    assert summary["evidence_status"] in {"evaluable", "not_evaluable"}


def test_validation_runner_runs_boundary_audit(tmp_path) -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")

    summary = run_validation_spec(_spec(), bundle, tmp_path, smoke=True)
    run_dir = tmp_path / summary["run_path"]
    audit = json.loads((run_dir / "boundary_audit.json").read_text(encoding="utf-8"))

    assert audit["passed"] is True
    assert summary["boundary_audit_passed"] is True


def test_validation_runner_separates_method_and_ablation_labels(tmp_path) -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")
    spec = ValidationRunSpec(
        scenario_id="sample_goa",
        method="random",
        ablation="capm_only",
        seed=23,
        budget=8,
        target_score=80,
    )

    summary = run_validation_spec(spec, bundle, tmp_path, smoke=True)

    assert summary["method"] == "random"
    assert summary["ablation"] == "capm_only"
    assert summary["strategy"] == "random"


def test_validation_runner_rejects_candidate_result_leakage(tmp_path) -> None:
    import pytest

    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")
    bundle["candidates"] = bundle["candidates"].assign(overall_score=[1] * len(bundle["candidates"]))

    with pytest.raises(ValueError, match="leakage"):
        run_validation_spec(_spec(), bundle, tmp_path, smoke=True)
