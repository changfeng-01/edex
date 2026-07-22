import json
from pathlib import Path

import numpy as np
import pandas as pd

from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.scorer import score_real_evaluation


def test_real_waveform_outputs_external_csv_evidence_metadata(tmp_path: Path):
    waveform = tmp_path / "waveform.csv"
    time = np.arange(0, 10, dtype=float) * 1e-6
    pd.DataFrame(
        {
            "XVAL": time,
            "v(o1)": np.where((time >= 1e-6) & (time < 4e-6), 6.0, 0.0),
            "v(o2)": np.where((time >= 2e-6) & (time < 5e-6), 6.0, 0.0),
        }
    ).to_csv(waveform, index=False)

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "outputs",
        high_threshold=5.0,
        low_threshold=1.0,
        output_nodes=["o1", "o2"],
    )

    summary = json.loads((tmp_path / "outputs" / "real_summary.json").read_text(encoding="utf-8"))
    score = json.loads((tmp_path / "outputs" / "score_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "outputs" / "run_manifest_real.json").read_text(encoding="utf-8"))

    for payload in [summary, score, manifest]:
        assert payload["data_source"] == "real_simulation_csv"
        assert payload["engineering_validity"] == "simulation_only"
        assert payload["evidence_level"] == "level_1_external_csv"
        assert payload["simulation_backend"] == "external_csv"
        assert payload["mock_used"] is False
        assert "pdk_available" not in payload
        assert "ngspice_available" not in payload
        assert "reportable_as_real_ngspice" not in payload
        assert payload["optimizer_claim_level"] == "candidate_generated"


def test_score_real_evaluation_ignores_retired_backend_metadata_from_legacy_summary():
    summary = {
        "All_pulses_exist": True,
        "Seq_pass": True,
        "FalseTriggerCount": 0,
        "Max_overlap_ratio": 0.0,
        "Max_ripple": 0.0,
        "Max_voltage_loss": 0.0,
        "Delay_std": 0.0,
        "VOH_min": 6.0,
        "high_threshold": 5.0,
        "evidence_level": "level_3_real_ngspice_sky130_pdk",
        "simulation_backend": "ngspice",
        "mock_used": False,
        "pdk_available": True,
        "ngspice_available": True,
        "reportable_as_real_ngspice": True,
        "optimizer_claim_level": "nominal_rerun_passed",
    }
    spec = {
        "max_overlap_ratio": 0.1,
        "max_ripple_v": 1.0,
        "max_voltage_loss_v": 1.0,
        "max_delay_std": 1.0,
        "min_voh_margin_v": 0.1,
        "weights": {},
    }

    score = score_real_evaluation(summary, [], spec)

    assert score["evidence_level"] == "level_1_external_csv"
    assert score["simulation_backend"] == "external_csv"
    assert "reportable_as_real_ngspice" not in score
