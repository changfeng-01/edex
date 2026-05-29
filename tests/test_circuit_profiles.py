from pathlib import Path

import pytest

from goa_eval.circuit_profiles import (
    load_circuit_profiles,
    resolve_circuit_profile,
    validate_profile_references,
)


def test_load_circuit_profiles_resolves_aliases_and_units():
    profiles = load_circuit_profiles(Path("config/circuit_profiles.yaml"))

    ota = resolve_circuit_profile("opamp", profiles)

    assert ota["name"] == "ota_general"
    assert ota["boundary"]["engineering_validity"] == "simulation_only"
    assert ota["metrics"]["static_power_w"]["maximum"] == 0.005
    assert ota["metrics"]["unity_gain_hz"]["minimum"] == 20_000_000.0
    assert ota["profile_source"].endswith("config/circuit_profiles.yaml")


def test_load_circuit_profiles_resolves_goa_8k_reference_profile():
    profiles = load_circuit_profiles(Path("config/circuit_profiles.yaml"))

    goa = resolve_circuit_profile("goa_8k", profiles)

    assert goa["name"] == "goa_8k_lcd_reference"
    assert goa["boundary"]["data_source"] == "real_simulation_csv"
    assert goa["boundary"]["engineering_validity"] == "simulation_only"
    assert goa["reference"]["load"]["rl_ohm"] == 7200.0
    assert goa["reference"]["load"]["cl_f"] == 728e-12
    assert goa["metrics"]["fall_time_s"]["maximum"] == 0.97e-6
    assert goa["metrics"]["rise_time_s"]["maximum"] == 1.93e-6
    assert goa["metrics"]["power_total_w"]["maximum"] == 0.10


def test_circuit_profile_loader_falls_back_to_sky130_profiles():
    profiles = load_circuit_profiles(Path("missing-circuit-profiles.yaml"))

    ota = resolve_circuit_profile("two_stage_opamp", profiles)

    assert ota["name"] == "ota"
    assert "dc_gain_db" in ota["metrics"]


def test_validate_profile_references_rejects_unknown_semantic_tags(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    semantics_file = tmp_path / "semantics.yaml"
    profile_file.write_text(
        """
profiles:
  demo:
    candidate_rules:
      dc_gain_db:
        - semantic_tags: [missing_tag]
          direction: increase
""".strip(),
        encoding="utf-8",
    )
    semantics_file.write_text(
        """
parameters:
  m1_width:
    values: ["1um"]
    semantic_tags: [input_pair_width]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing_tag"):
        validate_profile_references(profile_file=profile_file, semantics_file=semantics_file)
