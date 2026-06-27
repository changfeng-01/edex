from __future__ import annotations

from pathlib import Path

import pytest

from goa_eval.pia_ca_llso.scenario_registry import load_scenario, validate_scenario_bundle


def test_scenario_registry_loads_history_candidates_and_config() -> None:
    bundle = load_scenario(
        {
            "scenario_id": "sample_goa",
            "history_csv": "examples/pia_ca_llso/sample_history.csv",
            "candidate_csv": "examples/pia_ca_llso/sample_candidates.csv",
            "config": "config/pia_ca_llso_goa_profile.yaml",
            "boundary": {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            },
        }
    )

    validate_scenario_bundle(bundle)
    assert bundle["scenario_id"] == "sample_goa"
    assert not bundle["history"].empty
    assert not bundle["candidates"].empty
    assert bundle["config"]["target_score"] == 80


def test_scenario_registry_rejects_missing_files() -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario(
            {
                "scenario_id": "missing",
                "history_csv": "missing_history.csv",
                "candidate_csv": "examples/pia_ca_llso/sample_candidates.csv",
                "config": "config/pia_ca_llso_goa_profile.yaml",
            }
        )


def test_scenario_registry_records_claim_boundary() -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")

    assert bundle["boundary"]["data_source"] == "real_simulation_csv"
    assert bundle["boundary"]["engineering_validity"] == "simulation_only"
    assert bundle["boundary"]["must_resimulate"] is True


def test_scenario_registry_supports_local_fixture_marker() -> None:
    bundle = load_scenario("examples/pia_ca_llso/scenarios/sample_goa.yaml")

    assert bundle["source_type"] == "local_fixture"
    assert bundle["claim_boundary"] == "CI fixture for closed-loop behavior only"


def test_real_case_pack_manifest_requires_history_candidates_and_results(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "scenario_id: real_goa_case_001",
                "source_type: real_simulation_csv",
                "history_csv: history.csv",
                "candidate_csv: candidates.csv",
                "config: config.yaml",
                "boundary:",
                "  data_source: real_simulation_csv",
                "  engineering_validity: simulation_only",
                "  must_resimulate: true",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="result_dirs"):
        load_scenario(manifest)


def test_real_case_pack_manifest_requires_boundary_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "scenario_id: real_goa_case_001",
                "source_type: real_simulation_csv",
                "history_csv: history.csv",
                "candidate_csv: candidates.csv",
                "result_dirs: [generation_000]",
                "config: config.yaml",
                "boundary:",
                "  data_source: real_simulation_csv",
                "  engineering_validity: simulation_only",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must_resimulate"):
        load_scenario(manifest)


def test_real_case_pack_rejects_paper_digitized_as_real_simulation(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "scenario_id: real_goa_case_001",
                "source_type: paper_digitized",
                "claim_source_type: real_simulation_csv",
                "history_csv: history.csv",
                "candidate_csv: candidates.csv",
                "result_dirs: [generation_000]",
                "config: config.yaml",
                "boundary:",
                "  data_source: real_simulation_csv",
                "  engineering_validity: simulation_only",
                "  must_resimulate: true",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="paper_digitized"):
        load_scenario(manifest)
