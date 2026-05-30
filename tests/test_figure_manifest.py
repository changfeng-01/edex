import json
from pathlib import Path

import numpy as np
import pandas as pd

from goa_eval.real_waveform_eval import run_real_waveform_evaluation


def test_real_waveform_evaluation_writes_figure_manifest_for_pngs(tmp_path: Path):
    waveform = tmp_path / "waveform.csv"
    time = np.arange(0, 20, dtype=float) * 1e-6
    frame = pd.DataFrame({"XVAL": time})
    for index in range(1, 4):
        frame[f"v(o{index})"] = np.where((time >= index * 1e-6) & (time < index * 1e-6 + 4e-6), 6.0, 0.0)
    frame.to_csv(waveform, index=False)

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "outputs",
        high_threshold=5.0,
        low_threshold=1.0,
        output_nodes=["o1", "o2", "o3"],
    )

    manifest_path = tmp_path / "outputs" / "figures" / "figure_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    figure_names = {item["figure"] for item in manifest["figures"]}
    png_names = {path.name for path in (tmp_path / "outputs" / "figures").glob("*.png")}

    assert png_names <= figure_names
    first = manifest["figures"][0]
    assert first["generated_by"] == "run_real_waveform_evaluation"
    assert first["source_type"] == "matplotlib_local"
    assert first["ai_generated"] is False
    assert first["llm_used"] is False
    assert first["data_source"] == "real_simulation_csv"
    assert first["engineering_validity"] == "simulation_only"
    assert first["evidence_level"] == "level_1_external_csv"
    assert str(waveform) in first["input_data"]
