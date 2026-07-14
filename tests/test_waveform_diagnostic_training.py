from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from goa_eval.metrics import RealEvalConfig
from goa_eval.waveform_diagnostic_training import (
    ENGINEERING_VALIDITY,
    DATA_SOURCE,
    build_diagnostic_samples,
    identify_signal_role,
    parse_nominal_params,
    train_waveform_diagnostic_model,
)


def _synthetic_waveform_frame() -> pd.DataFrame:
    time = np.arange(0.0, 24e-6, 0.5e-6)
    raw = np.where((time >= 2e-6) & (time <= 8e-6), 22.0, -8.0)
    mid = np.where((time >= 2.5e-6) & (time <= 8.5e-6), 21.0, -8.0)
    far = np.where((time >= 3.0e-6) & (time <= 9.0e-6), 19.0, -8.2)
    do = np.where((time >= 1e-6) & (time <= 12e-6), 10.2, 0.2)
    de = np.where((time >= 12e-6) & (time <= 20e-6), 10.2, 0.2)
    return pd.DataFrame(
        {
            "time": time,
            "g<2>": raw,
            "gate_mid<2>": mid,
            "gate_far<2>": far,
            "do": do,
            "de": de,
            "do_far": do - 0.4,
            "xi8<1>.pixel": do - 0.6,
            "com": np.full_like(time, 5.2),
            "xi0<2>.xi0<1>.pu": raw + 5.0,
            "xi0<91>.xi0<4>.pu": raw + 8.0,
        }
    )


def test_identify_signal_roles_for_cgg_nodes() -> None:
    assert identify_signal_role("clk<8>")["signal_role"] == "clock_source"
    assert identify_signal_role("gate_far<720>")["position"] == "far"
    assert identify_signal_role("xi8<9>.pixel")["signal_role"] == "pixel_electrode"
    dummy = identify_signal_role("xi0<91>.xi0<4>.pu")
    assert dummy["signal_role"] == "goa_internal"
    assert dummy["position"] == "tail_dummy"


def test_build_diagnostic_samples_extracts_reference_features_and_boundaries(tmp_path: Path) -> None:
    nominal = tmp_path / "nominal.sp"
    nominal.write_text(".param\n+VGH=22V\n+VGL=-8V\n", encoding="utf-8")
    params = parse_nominal_params(nominal)
    samples = build_diagnostic_samples(_synthetic_waveform_frame(), config=RealEvalConfig(), nominal_params=params)

    assert {"gate_raw", "gate_line", "pixel_electrode", "goa_internal"} <= set(samples["signal_role"])
    far = samples[samples["node"].eq("gate_far<2>")].iloc[0]
    assert far["reference_node"] == "g<2>"
    assert float(far["propagation_delay_to_reference_s"]) > 0
    assert float(far["voltage_loss_vs_reference_v"]) > 0
    pixel = samples[samples["node"].eq("xi8<1>.pixel")].iloc[0]
    assert float(pixel["pixel_tracking_error_rms_v"]) > 0
    assert set(samples["data_source"]) == {DATA_SOURCE}
    assert set(samples["engineering_validity"]) == {ENGINEERING_VALIDITY}


def test_train_waveform_diagnostic_model_writes_expected_artifacts(tmp_path: Path) -> None:
    waveform = tmp_path / "waveform.csv"
    frame = _synthetic_waveform_frame().rename(columns={column: f"v({column})" for column in _synthetic_waveform_frame().columns if column != "time"})
    frame = frame.rename(columns={"time": "XVAL"})
    frame.to_csv(waveform, index=False)
    nominal = tmp_path / "nominal.sp"
    nominal.write_text(".param\n+VGH=22V\n+VGL=-8V\n+Wt1=500u\n", encoding="utf-8")
    netlist = tmp_path / "design.netlist"
    netlist.write_text(".SUBCKT demo\n.ENDS\n", encoding="utf-8")
    model_card = tmp_path / "goa.mod.sp"
    model_card.write_text(".model m_goa_tft nmos\n", encoding="utf-8")

    out = tmp_path / "out"
    artifacts = train_waveform_diagnostic_model(
        waveform_path=waveform,
        nominal_sp=nominal,
        netlist=netlist,
        model_cards=[model_card],
        output_dir=out,
        random_state=7,
    )

    assert artifacts.report["data_source"] == DATA_SOURCE
    for name in [
        "diagnostic_samples.csv",
        "diagnostic_feature_matrix.csv",
        "diagnostic_predictions.csv",
        "diagnostic_model.joblib",
        "feature_importance.csv",
        "diagnostic_model_report.json",
        "diagnostic_model_card.md",
    ]:
        assert (out / name).exists()
    report = json.loads((out / "diagnostic_model_report.json").read_text(encoding="utf-8"))
    assert report["engineering_validity"] == ENGINEERING_VALIDITY
    assert report["must_resimulate"] is True
    predictions = pd.read_csv(out / "diagnostic_predictions.csv")
    assert "predicted_risk_level" in predictions.columns
    assert predictions["data_source"].eq(DATA_SOURCE).all()
