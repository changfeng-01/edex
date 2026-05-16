from pathlib import Path
import json

import numpy as np
import pandas as pd

from goa_eval.config import load_real_spec
from goa_eval.cli import build_parser
from goa_eval.metrics import RealEvalConfig, evaluate_waveform_metrics
from goa_eval.real_waveform_eval import build_output_nodes, run_real_waveform_evaluation


def _large_frame(stage_count: int = 720, *, degraded_stage: int | None = None) -> pd.DataFrame:
    time = np.arange(0.0, 100.0e-6, 0.1e-6)
    data = {"time": time}
    for index in range(1, stage_count + 1):
        start = 2.0e-6 + index * 0.1e-6
        high = 8.0 - index * 0.001
        if degraded_stage == index:
            high = 4.0
        data[f"o{index}"] = np.where((time >= start) & (time < start + 2.5e-6), high, 0.0)
    return pd.DataFrame(data)


def test_real_spec_generates_720_output_nodes(tmp_path: Path):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
thresholds:
  high_threshold: 5.0
cascade:
  stage_count: 720
  output_node_pattern: "o{index}"
  stage_group_size: 60
  sample_nodes: [1, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720]
""",
        encoding="utf-8",
    )

    spec = load_real_spec(spec_path)
    nodes = build_output_nodes(spec)

    assert len(nodes) == 720
    assert nodes[:3] == ["o1", "o2", "o3"]
    assert nodes[-1] == "o720"
    assert spec["cascade"]["stage_group_size"] == 60


def test_evaluate_real_cli_accepts_cascade_overrides():
    args = build_parser().parse_args(
        [
            "evaluate-real",
            "--waveform",
            "waveform.csv",
            "--stage-count",
            "720",
            "--output-node-pattern",
            "o{index}",
            "--stage-group-size",
            "60",
        ]
    )

    assert args.stage_count == 720
    assert args.output_node_pattern == "o{index}"
    assert args.stage_group_size == 60


def test_720_stage_metrics_include_blocks_worst_stage_and_trends():
    output_nodes = [f"o{index}" for index in range(1, 721)]
    result = evaluate_waveform_metrics(
        _large_frame(degraded_stage=123),
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=0.5e-6, max_overlap_ratio=1.0, stage_group_size=60),
        output_nodes=output_nodes,
    )

    assert len(result.stage_rows) == 720
    assert result.summary["stage_count"] == 720
    assert len(result.summary["block_summary"]) == 12
    assert result.summary["block_summary"][0]["stage_start"] == 1
    assert result.summary["block_summary"][-1]["stage_end"] == 720
    assert result.summary["first_failed_stage"] == 123
    assert result.summary["worst_stage"] == 123
    assert result.summary["VOH_slope"] < 0
    assert "VOH_p1" in result.summary
    assert "VoltageLoss_p95" in result.summary
    assert "Delay_p95" in result.summary
    assert "Ripple_p95" in result.summary


def test_run_real_waveform_evaluation_writes_720_stage_outputs(tmp_path: Path):
    frame = _large_frame()
    waveform = tmp_path / "waveform.csv"
    frame.rename(columns={column: f"v({column})" for column in frame.columns if column != "time"}).rename(columns={"time": "XVAL"}).to_csv(waveform, index=False)
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
thresholds:
  high_threshold: 5.0
  low_threshold: 1.0
  target_pulse_width_us: 2.5
  pulse_width_tolerance_us: 2.0
  max_overlap_ratio: 1.0
  max_ripple_v: 0.5
  max_voltage_loss_v: 0.5
  max_delay_std_us: 1.0
  min_voh_margin_v: 1.0
  target_refresh_hz: 60.0
cascade:
  stage_count: 720
  output_node_pattern: "o{index}"
  stage_group_size: 60
  sample_nodes: [1, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720]
""",
        encoding="utf-8",
    )

    out = tmp_path / "outputs"
    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=out,
        spec_path=spec_path,
    )

    metrics = pd.read_csv(out / "real_metrics.csv")
    summary = json.loads((out / "real_summary.json").read_text(encoding="utf-8"))
    report = (out / "real_waveform_report.md").read_text(encoding="utf-8")

    assert len(metrics) == 720
    assert summary["stage_count"] == 720
    assert len(summary["block_summary"]) == 12
    assert "大规模级联摘要报告" in report
    assert "分段摘要" in report
    assert (out / "figures" / "voh_trend.png").exists()
    assert (out / "figures" / "voltage_loss_trend.png").exists()
    assert (out / "figures" / "delay_trend.png").exists()
    assert (out / "figures" / "ripple_trend.png").exists()
    assert (out / "figures" / "block_stability_heatmap.png").exists()
    assert (out / "figures" / "sample_outputs_overview.png").exists()
    assert (out / "figures" / "sample_outputs_stacked.png").exists()
