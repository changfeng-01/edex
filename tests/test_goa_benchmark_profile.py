import json
from pathlib import Path

from goa_eval.real_waveform_eval import run_real_waveform_evaluation


def test_evaluate_real_writes_goa_benchmark_metrics_and_report_section(tmp_path):
    output_dir = tmp_path / "goa_profile_run"

    run_real_waveform_evaluation(
        waveform_path=Path("examples/sample_waveform.csv"),
        internal_waveform_path=None,
        output_dir=output_dir,
        spec_path=Path("config/spec.yaml"),
        circuit_profile="goa_8k_lcd_reference",
        profile_file=Path("config/circuit_profiles.yaml"),
    )

    analysis = json.loads((output_dir / "analysis_metrics.json").read_text(encoding="utf-8"))
    score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
    report = (output_dir / "real_waveform_report.md").read_text(encoding="utf-8")

    metrics = analysis["goa_benchmark_metrics"]
    assert metrics["benchmark_scope"] == "literature_reference"
    assert metrics["fall_time_s"] is not None
    assert metrics["rise_time_s"] is not None
    assert metrics["false_trigger_count"] == 0
    assert metrics["reference_tfall_s"] == 0.97e-6
    assert metrics["reference_trise_s"] == 1.93e-6
    assert metrics["reference_load_rl_ohm"] == 7200.0
    assert metrics["reference_load_cl_f"] == 728e-12
    comparisons = metrics["baseline_comparisons"]
    assert "sharp_like_goa" in comparisons
    assert comparisons["sharp_like_goa"]["metrics"]["fall_time_s"]["status"] == "evaluated"
    assert comparisons["sharp_like_goa"]["metrics"]["fall_time_s"]["relative_improvement"] is not None
    assert comparisons["sharp_like_goa"]["metrics"]["power_total_w"]["status"] == "not_evaluable"
    assert "missing current power_total_w" in comparisons["sharp_like_goa"]["metrics"]["power_total_w"]["not_evaluable_reason"]
    assert "power_total_w" in score["not_evaluable_metrics"]
    assert "area_proxy" in score["not_evaluable_metrics"]
    assert score["cost_score"] < 100.0
    assert "## 7. GOA 论文 benchmark 对比" in report
    assert "### 7.1 维度分组" in report
    assert "### 7.2 文献 baseline 归一化对比" in report
    assert "文献基线，不是本仓库复现仿真结果" in report
    assert "engineering_validity = simulation_only" in report
