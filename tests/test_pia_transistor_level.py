from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from goa_eval.cli import main
from goa_eval.circuit_profiles import load_circuit_profiles, resolve_circuit_profile
from goa_eval.pia_ca_llso.features import extract_physics_features
from goa_eval.pia_ca_llso.selector import select_candidates
from goa_eval.pia_ca_llso.simulation_contract import build_simulation_batch
from goa_eval.pia_ca_llso.transistor_level_adapter import (
    build_transistor_level_netlists,
    import_transistor_level_results,
)


ROOT = Path(__file__).resolve().parents[1]
TRANSISTOR_CONFIG = ROOT / "config" / "pia_ca_llso_transistor_profile.yaml"
TRANSISTOR_EXAMPLES = ROOT / "examples" / "transistor_level_goa"


def _config() -> dict:
    return yaml.safe_load(TRANSISTOR_CONFIG.read_text(encoding="utf-8"))


def test_transistor_level_circuit_profile_resolves_boundary() -> None:
    profiles = load_circuit_profiles(ROOT / "config" / "circuit_profiles.yaml")

    profile = resolve_circuit_profile("pia_transistor_level", profiles)

    assert profile["name"] == "transistor_level_goa"
    assert profile["boundary"]["data_source"] == "real_simulation_csv"
    assert profile["boundary"]["engineering_validity"] == "simulation_only"
    assert profile["boundary"]["must_resimulate"] is True
    assert "delay_s" in profile["hard_constraints"]


def test_transistor_level_features_use_device_instance_columns_without_result_leakage() -> None:
    frame = pd.DataFrame(
        [
            {
                "M_pullup_W": 420,
                "M_pullup_L": 5,
                "M_pulldown_W": 210,
                "M_pulldown_L": 5,
                "M_reset_W": 160,
                "M_reset_L": 5,
                "M_bootstrap_W": 120,
                "M_bootstrap_L": 5,
                "C_load": 1.0,
                "C_boot": 2.0,
                "VDD": 5,
                "VSS": 0,
                "VGH": 15,
                "VGL": -5,
                "Vth_shift": 1.2,
                "CLK_rise_time": 0.10,
                "CLK_fall_time": 0.10,
                "overall_score": 99,
            }
        ]
    )

    features, report = extract_physics_features(frame, _config()["physics_features"])

    assert features.loc[0, "pullup_w_l"] == 84
    assert features.loc[0, "pullup_pulldown_ratio"] == 2
    assert features.loc[0, "drive_to_load_ratio"] > 100
    assert features.loc[0, "supply_swing"] == 5
    assert report["profile"] == "transistor_level"
    assert report["leakage_violations"] == []


def test_active_influence_on_demand_selects_transistor_level_candidates() -> None:
    history = pd.read_csv(TRANSISTOR_EXAMPLES / "sample_history.csv")
    candidates = pd.read_csv(TRANSISTOR_EXAMPLES / "sample_candidates_pre_sim.csv")

    result = select_candidates(
        candidates,
        history,
        strategy="active_influence_on_demand",
        top_k=3,
        config=_config(),
    )

    selected = result.selected_candidates
    assert len(selected) == 3
    assert "active_influence_on_demand_score" in selected.columns
    assert all(selected["data_source"] == "real_simulation_csv")
    assert all(selected["engineering_validity"] == "simulation_only")
    assert all(selected["must_resimulate"])


def test_transistor_level_adapter_renders_netlists_and_imports_external_results(tmp_path: Path) -> None:
    config = _config()
    candidates = pd.read_csv(TRANSISTOR_EXAMPLES / "sample_candidates_pre_sim.csv").head(2)
    batch, batch_manifest = build_simulation_batch(candidates, config, generation=1)

    netlists, netlist_manifest = build_transistor_level_netlists(
        batch,
        template_path=TRANSISTOR_EXAMPLES / "template.spice",
        output_dir=tmp_path,
        parameter_columns=config["parameter_columns"],
    )

    first_netlist = Path(netlists.loc[0, "netlist_path"])
    assert batch_manifest["data_source"] == "real_simulation_csv"
    assert netlist_manifest["claim_boundary"].startswith("rendered netlists")
    assert first_netlist.exists()
    assert "Mpu out clk vgh vgh tft_model W=430" in first_netlist.read_text(encoding="utf-8")
    assert all(netlists["must_resimulate"])

    imported = import_transistor_level_results(
        TRANSISTOR_EXAMPLES / "expected_results.csv",
        batch,
        config,
        generation=1,
    )

    assert list(imported["candidate_id"]) == ["tc1", "tc2"]
    assert all(imported["data_source"] == "real_simulation_csv")
    assert all(imported["engineering_validity"] == "simulation_only")
    assert not imported["must_resimulate"].any()
    assert "M_pullup_W" in imported.columns


def test_transistor_level_render_cli_writes_netlist_index(tmp_path: Path) -> None:
    candidates = pd.read_csv(TRANSISTOR_EXAMPLES / "sample_candidates_pre_sim.csv").head(1)
    batch_path = tmp_path / "simulation_batch.csv"
    candidates.to_csv(batch_path, index=False)
    output_dir = tmp_path / "rendered"

    exit_code = main(
        [
            "pia-render-transistor-netlists",
            "--simulation-batch",
            str(batch_path),
            "--template",
            str(TRANSISTOR_EXAMPLES / "template.spice"),
            "--config",
            str(TRANSISTOR_CONFIG),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "transistor_level_netlists.csv").exists()
    manifest = yaml.safe_load((output_dir / "transistor_level_netlist_manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_source"] == "real_simulation_csv"
    assert manifest["engineering_validity"] == "simulation_only"
    assert manifest["must_resimulate"] is True
