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


def test_load_circuit_profiles_rejects_duplicate_aliases(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  ota:
    aliases: [shared]
    metrics: {}
  comparator:
    aliases: [shared]
    metrics: {}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate circuit profile alias.*shared"):
        load_circuit_profiles(profile_file)


def test_load_circuit_profiles_rejects_metric_from_unsupported_analysis(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  ota:
    aliases: []
    required_analyses: [op]
    metrics:
      dc_gain_db:
        source: ac_metrics
        source_analysis: ac
        unit: dB
        minimum: 40dB
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="dc_gain_db.*unsupported analysis: ac"):
        load_circuit_profiles(profile_file)


def test_load_circuit_profiles_rejects_unknown_required_metric_and_wrong_units(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  oscillator:
    aliases: []
    required_analyses: [tran]
    metrics:
      frequency_hz:
        source: tran_metrics
        source_analysis: tran
        unit: Hz
        minimum: 2mV
    hard_constraints:
      missing_metric:
        maximum: 1
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as error:
        load_circuit_profiles(profile_file)

    assert "missing_metric" in str(error.value)
    assert "2mV" in str(error.value)
