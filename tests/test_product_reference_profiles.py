import json
from pathlib import Path

import pytest

from goa_eval.analysis_metrics import extract_analysis_metrics
from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile


CASES = {
    "ota": "ota_general",
    "comparator": "comparator_general",
    "oscillator": "oscillator_general",
}


@pytest.mark.parametrize(("fixture_name", "profile_id"), CASES.items())
def test_reference_profile_runs_generalized_analysis_with_provenance(fixture_name, profile_id):
    fixture = Path("examples/product_profiles") / fixture_name
    expected = json.loads((fixture / "expected_summary.json").read_text(encoding="utf-8"))
    profiles = load_circuit_profiles(Path("config/circuit_profiles.yaml"))
    profile = resolve_circuit_profile(profile_id, profiles)

    assert profile["name"] == profile_id
    assert profile["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
    }
    for analysis in profile["required_analyses"]:
        assert (fixture / f"{analysis}_metrics.csv").is_file()

    analysis = extract_analysis_metrics(fixture, topology_profile=profile_id)

    assert analysis["topology_profile"] == profile_id
    for metric, contract in expected["metrics"].items():
        section = contract["source"]
        assert analysis[section][metric] == pytest.approx(contract["value"])
        provenance = analysis["metric_provenance"][f"{section}.{metric}"]
        assert provenance["unit"] == profile["metrics"][metric]["unit"]
        assert provenance["source_file"] == f"{section}.csv"
        assert provenance["source_analysis"] == profile["metrics"][metric]["source_analysis"]

    assert "goa_benchmark_metrics" not in analysis
    assert not any("goa" in metric.lower() for metric in expected["metrics"])


def test_reference_profiles_do_not_modify_product_core_models():
    source = Path("src/goa_eval/product/models.py").read_text(encoding="utf-8")

    for circuit_name in ("Ota", "Comparator", "Oscillator"):
        assert f"class {circuit_name}" not in source
