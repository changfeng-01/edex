import json
import shutil
from pathlib import Path

from goa_eval.product.analysis_service import AnalysisService
from goa_eval.web.runners import run_uploaded_case
from goa_eval.web.schemas import UploadedCaseConfig


def _prepare_case(root: Path) -> Path:
    case_dir = root / "case"
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True)
    shutil.copyfile("examples/sample_waveform.csv", input_dir / "waveform.csv")
    shutil.copyfile("examples/sample_params.yaml", input_dir / "params.yaml")
    return case_dir


def _parity_values(analysis_dir: Path) -> dict[str, object]:
    summary = json.loads((analysis_dir / "real_summary.json").read_text(encoding="utf-8"))
    score = json.loads((analysis_dir / "score_summary.json").read_text(encoding="utf-8"))
    return {
        "Overall_status": summary["Overall_status"],
        "overall_score": score["overall_score"],
        "hard_constraint_passed": score["hard_constraint_passed"],
        "stage_count": summary["stage_count"],
        "VOH_min": summary["VOH_min"],
        "Max_ripple": summary["Max_ripple"],
        "data_source": summary["data_source"],
        "engineering_validity": summary["engineering_validity"],
        "must_resimulate": summary["must_resimulate"],
    }


def test_legacy_runner_delegates_to_shared_analysis_service(tmp_path, monkeypatch):
    case_dir = _prepare_case(tmp_path)
    called = []
    original = AnalysisService.execute_compatibility

    def tracked(self, **kwargs):
        called.append(kwargs["case_id"])
        return original(self, **kwargs)

    monkeypatch.setattr(AnalysisService, "execute_compatibility", tracked)

    result = run_uploaded_case(case_dir, UploadedCaseConfig(case_id="legacy_adapter"))

    assert result.status == "completed"
    assert called == ["legacy_adapter"]


def test_legacy_and_shared_pipeline_return_identical_core_results(tmp_path):
    legacy_case = _prepare_case(tmp_path / "legacy")
    shared_case = _prepare_case(tmp_path / "shared")
    config = UploadedCaseConfig(case_id="parity", generate_candidates=True)

    legacy_result = run_uploaded_case(legacy_case, config)
    AnalysisService(None, None).execute_compatibility(
        input_dir=shared_case / "input",
        analysis_dir=shared_case / "analysis",
        product_demo_root=shared_case / "product_demo",
        case_id=config.case_id,
        config=config,
    )

    assert legacy_result.status == "completed"
    assert _parity_values(legacy_case / "analysis") == _parity_values(shared_case / "analysis")
