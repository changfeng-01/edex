from pathlib import Path

import pandas as pd

from goa_eval.multi_agent.tools import (
    check_schema_and_boundary,
    generate_candidates,
    inspect_candidates,
    inspect_analysis_metrics,
    inspect_existing_reports,
    inspect_leaderboard,
    inspect_optimization_history,
    inspect_optimization_leaderboard,
    inspect_netlist_integrity,
    inspect_real_metrics,
    inspect_real_summary,
    inspect_run_manifest,
    inspect_score_summary,
    inspect_task_inputs,
    inspect_validation_summary,
    normalize_artifact_inputs,
)
from goa_eval.multi_agent.tool_registry import get_tool_registry


EXAMPLES = Path("examples/multi_agent")


def test_inspect_task_inputs_reports_file_availability():
    result = inspect_task_inputs(
        {
            "leaderboard": str(EXAMPLES / "sample_sky130_leaderboard.csv"),
            "missing": str(EXAMPLES / "missing.csv"),
        }
    )

    assert result.status == "warning"
    assert result.data["available_inputs"]["leaderboard"]["exists"] is True
    assert result.data["available_inputs"]["missing"]["exists"] is False


def test_inspect_leaderboard_extracts_best_candidate():
    result = inspect_leaderboard(EXAMPLES / "sample_sky130_leaderboard.csv")

    assert result.status == "pass"
    assert result.data["row_count"] >= 1
    assert result.data["best_candidate"]["candidate_id"] == "sky_cand_001"
    assert "overall_score" in result.data["best_candidate"]


def test_inspect_score_summary_preserves_boundary_fields():
    result = inspect_score_summary(EXAMPLES / "sample_score_summary.json")

    assert result.status == "pass"
    assert result.data["data_source"] == "real_simulation_csv"
    assert result.data["engineering_validity"] == "simulation_only"


def test_inspect_real_metrics_detects_bad_cells():
    result = inspect_real_metrics(EXAMPLES / "sample_real_metrics.csv")

    assert result.status == "warning"
    assert result.data["row_count"] >= 1
    assert result.data["bad_cell_count"] >= 1


def test_generate_and_inspect_candidates_uses_optimizer_wrapper(tmp_path):
    generated = generate_candidates(
        leaderboard_path=EXAMPLES / "sample_sky130_leaderboard.csv",
        param_space_path=Path("examples/sample_params.yaml"),
        output_dir=tmp_path,
        max_candidates=3,
    )
    candidate_path = Path(generated.data["next_candidates_path"])

    assert generated.status in {"pass", "warning"}
    assert candidate_path.exists()
    assert len(pd.read_csv(candidate_path)) <= 3

    inspected = inspect_candidates(candidate_path, Path("examples/sample_params.yaml"), max_parameter_changes=2)
    assert inspected.status in {"pass", "warning"}
    assert inspected.data["candidate_count"] <= 3


def test_check_schema_and_boundary_warns_on_missing_boundary(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text('{"schema_version":"1.0"}', encoding="utf-8")

    result = check_schema_and_boundary(path, "real_simulation_csv", "simulation_only")

    assert result.status == "warning"
    assert any("data_source" in issue for issue in result.data["issues"])


def test_inspect_netlist_integrity_detects_incomplete_netlist(tmp_path):
    netlist = tmp_path / "bad.sp"
    netlist.write_text(
        "\n".join(
            [
                ".SUBCKT only in out",
                "R1 in out 1k",
            ]
        ),
        encoding="utf-8",
    )

    result = inspect_netlist_integrity(netlist)

    assert result.status == "warning"
    assert any("netlist missing .END" in issue for issue in result.warnings)
    assert any(".SUBCKT without matching .ENDS" in issue for issue in result.warnings)
    assert any("netlist missing MOS devices" in issue for issue in result.warnings)


def test_normalize_artifact_inputs_discovers_current_main_artifacts(tmp_path):
    (tmp_path / "real_summary.json").write_text('{"data_source":"real_simulation_csv","engineering_validity":"simulation_only"}', encoding="utf-8")
    (tmp_path / "real_metrics.csv").write_text("stage,OverlapRatio\n1,0.0\n", encoding="utf-8")
    (tmp_path / "score_summary.json").write_text('{"data_source":"real_simulation_csv","engineering_validity":"simulation_only"}', encoding="utf-8")
    (tmp_path / "optimization_leaderboard.csv").write_text("candidate_id,overall_score\ncand_001,0.9\n", encoding="utf-8")
    (tmp_path / "best_next_candidates.csv").write_text("candidate_id,parameter,candidate_values\ncand_002,load_cap,[1p]\n", encoding="utf-8")

    normalized = normalize_artifact_inputs({"artifact_dir": str(tmp_path)})

    assert normalized["real_summary"].endswith("real_summary.json")
    assert normalized["real_metrics"].endswith("real_metrics.csv")
    assert normalized["score_summary"].endswith("score_summary.json")
    assert normalized["leaderboard"].endswith("optimization_leaderboard.csv")
    assert normalized["next_candidates"].endswith("best_next_candidates.csv")


def test_evidence_tools_are_registered():
    registry = get_tool_registry()

    for tool_name in [
        "inspect_artifact_bundle",
        "inspect_real_summary",
        "inspect_analysis_metrics",
        "inspect_optimization_history",
        "inspect_optimization_leaderboard",
        "inspect_validation_summary",
        "inspect_run_manifest",
        "inspect_existing_reports",
    ]:
        assert tool_name in registry


def test_evidence_inspectors_summarize_mainline_artifacts(tmp_path):
    real_summary = tmp_path / "real_summary.json"
    real_summary.write_text(
        '{"data_source":"real_simulation_csv","engineering_validity":"simulation_only","Max_overlap_ratio":0.03,"FalseTriggerCount":0}',
        encoding="utf-8",
    )
    analysis_metrics = tmp_path / "analysis_metrics.json"
    analysis_metrics.write_text('{"topology_profile":"ota","not_evaluable_metrics":["unity_gain_hz"]}', encoding="utf-8")
    history = tmp_path / "optimization_history.json"
    history.write_text(
        '{"rounds":[{"round_index":1,"best_score":0.81,"best_run_dir":"round_1"},{"round_index":2,"best_score":0.91,"best_run_dir":"round_2","target_status":"passed"}],"stop_reason":"target_met"}',
        encoding="utf-8",
    )
    leaderboard = tmp_path / "optimization_leaderboard.csv"
    leaderboard.write_text("candidate_id,overall_score,target.status\ncand_2,0.91,passed\ncand_1,0.81,failed\n", encoding="utf-8")
    validation = tmp_path / "validation_summary.csv"
    validation.write_text("target.status,metric\nfailed,Max_ripple\n", encoding="utf-8")
    manifest = tmp_path / "run_manifest_real.json"
    manifest.write_text('{"data_source":"real_simulation_csv","engineering_validity":"simulation_only","run_id":"r1"}', encoding="utf-8")
    report = tmp_path / "diagnosis_report.md"
    report.write_text("simulation_only diagnosis", encoding="utf-8")

    assert inspect_real_summary(real_summary).data["boundary"]["data_source"] == "real_simulation_csv"
    assert inspect_analysis_metrics(analysis_metrics).data["not_evaluable_metrics"] == ["unity_gain_hz"]
    history_result = inspect_optimization_history(history)
    assert history_result.data["round_count"] == 2
    assert history_result.data["best_score"] == 0.91
    assert history_result.data["best_run_dir"] == "round_2"
    assert history_result.data["target_status"] == "passed"
    assert inspect_optimization_leaderboard(leaderboard).data["best_candidate"]["candidate_id"] == "cand_2"
    assert inspect_validation_summary(validation).status == "warning"
    assert inspect_run_manifest(manifest).data["boundary"]["engineering_validity"] == "simulation_only"
    assert inspect_existing_reports({"diagnosis_report": str(report)}).data["reports"]["diagnosis_report"]["exists"] is True
