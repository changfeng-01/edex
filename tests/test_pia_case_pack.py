from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from goa_eval.cli import main
from goa_eval.pia_ca_llso.case_pack import (
    case_pack_to_protocol,
    export_case_pack_template,
    load_case_pack,
)
from goa_eval.pia_ca_llso.case_pack_validation import validate_case_pack


def _write_case_pack(
    root: Path,
    *,
    scenario_id: str = "goa_case_001",
    include_results: bool = True,
    candidate_leakage: bool = False,
    missing_candidate_id: bool = False,
) -> Path:
    pack = root / scenario_id
    pack.mkdir(parents=True)
    history = pd.DataFrame(
        [
            {
                "sample_id": "h1",
                "candidate_id": "c_hist",
                "overall_score": 62.0,
                "hard_constraint_passed": True,
                "C_boot": 2.0,
                "C_load": 1.0,
            }
        ]
    )
    candidate_rows = [
        {"candidate_id": "c1", "C_boot": 2.2, "C_load": 1.1},
        {"candidate_id": "c2", "C_boot": 1.8, "C_load": 1.3},
    ]
    candidates = pd.DataFrame(candidate_rows)
    if missing_candidate_id:
        candidates = candidates.drop(columns=["candidate_id"])
    if candidate_leakage:
        candidates["overall_score"] = [95.0, 40.0]
        candidates["hard_constraint_passed"] = [True, False]
    results = pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "method": "pia_full",
                "seed": 1,
                "budget_index": 1,
                "overall_score": 91.0,
                "hard_constraint_passed": True,
            },
            {
                "candidate_id": "c2",
                "method": "pia_no_repair",
                "seed": 1,
                "budget_index": 1,
                "overall_score": 70.0,
                "hard_constraint_passed": True,
            },
        ]
    )
    history.to_csv(pack / "history.csv", index=False)
    candidates.to_csv(pack / "candidate_pool.csv", index=False)
    if include_results:
        results.to_csv(pack / "simulation_results.csv", index=False)
    (pack / "scoring_config.yaml").write_text("target_score: 80\n", encoding="utf-8")
    (pack / "provenance.json").write_text(json.dumps({"source": "unit_fixture"}), encoding="utf-8")
    (pack / "scenario.yaml").write_text(
        yaml.safe_dump(
            {
                "scenario_id": scenario_id,
                "history_csv": "history.csv",
                "candidate_csv": "candidate_pool.csv",
                "result_csv": "simulation_results.csv",
                "methods": ["pia_full", "pia_no_repair"],
                "seeds": [1],
                "top_k": 1,
                "target_score": 80,
                "evidence_boundary": {
                    "data_source": "real_simulation_csv",
                    "engineering_validity": "simulation_only",
                    "must_resimulate": True,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return pack


def test_case_pack_template_contains_required_files(tmp_path: Path) -> None:
    template_dir = tmp_path / "template"

    export_case_pack_template(template_dir)

    assert {
        "scenario.yaml",
        "history.csv",
        "candidate_pool.csv",
        "simulation_results.csv",
        "scoring_config.yaml",
        "provenance.json",
    }.issubset({path.name for path in template_dir.iterdir()})
    scenario = yaml.safe_load((template_dir / "scenario.yaml").read_text(encoding="utf-8"))
    assert scenario["history_csv"] == "history.csv"
    assert scenario["candidate_csv"] == "candidate_pool.csv"
    assert scenario["result_csv"] == "simulation_results.csv"
    assert scenario["evidence_boundary"]["data_source"] == "real_simulation_csv"
    assert scenario["evidence_boundary"]["engineering_validity"] == "simulation_only"
    assert scenario["evidence_boundary"]["must_resimulate"] is True


def test_case_pack_validator_rejects_missing_candidate_id(tmp_path: Path) -> None:
    pack = _write_case_pack(tmp_path, missing_candidate_id=True)

    with pytest.raises(ValueError, match="candidate_id"):
        validate_case_pack(pack)


def test_case_pack_validator_rejects_result_leakage_in_candidate_pool(tmp_path: Path) -> None:
    pack = _write_case_pack(tmp_path, candidate_leakage=True)

    with pytest.raises(ValueError, match="leakage"):
        validate_case_pack(pack)


def test_case_pack_validator_accepts_evidence_missing_when_not_strict(tmp_path: Path) -> None:
    pack = _write_case_pack(tmp_path, include_results=False)

    result = validate_case_pack(pack, strict_evidence=False)

    assert result["evidence_available"] is False
    assert result["selection_only"] is True
    assert result["included_in_statistical_claim"] is False


def test_case_pack_validator_fails_evidence_missing_when_strict(tmp_path: Path) -> None:
    pack = _write_case_pack(tmp_path, include_results=False)

    with pytest.raises(ValueError, match="simulation_results"):
        validate_case_pack(pack, strict_evidence=True)


def test_case_pack_loader_converts_to_multiscenario_protocol(tmp_path: Path) -> None:
    pack_dir = _write_case_pack(tmp_path)
    case_pack = load_case_pack(pack_dir)

    protocol = case_pack_to_protocol([case_pack])

    assert protocol["target_score"] == 80
    assert protocol["top_k"] == 1
    assert protocol["methods"] == ["pia_full", "pia_no_repair"]
    assert protocol["seeds"] == [1]
    assert protocol["scenarios"][0]["scenario_id"] == "goa_case_001"
    assert protocol["scenarios"][0]["history_csv"].endswith("history.csv")
    assert protocol["scenarios"][0]["candidate_csv"].endswith("candidate_pool.csv")
    assert protocol["scenarios"][0]["result_csv"].endswith("simulation_results.csv")
    assert protocol["boundary"]["data_source"] == "real_simulation_csv"
    assert protocol["boundary"]["engineering_validity"] == "simulation_only"
    assert protocol["boundary"]["must_resimulate"] is True


def test_pia_validate_case_pack_root_runs_and_writes_publication_report(tmp_path: Path) -> None:
    pack_root = tmp_path / "case_packs"
    _write_case_pack(pack_root, scenario_id="case_a")
    output_dir = tmp_path / "out"

    assert main(
        [
            "pia-validate",
            "--case-pack-root",
            str(pack_root),
            "--output-dir",
            str(output_dir),
            "--strict-evidence",
        ]
    ) == 0

    expected = {
        "case_pack_validation.json",
        "case_pack_validation.md",
        "publication_evidence_inventory.csv",
        "publication_summary.csv",
        "publication_win_rates.csv",
        "publication_claim_boundary_checklist.md",
        "publication_report.md",
        "source_lock.json",
    }
    assert expected.issubset({path.name for path in output_dir.iterdir()})
    source_lock = json.loads((output_dir / "source_lock.json").read_text(encoding="utf-8"))
    assert "input_files" in source_lock
    assert "python_version" in source_lock
    assert "git_commit" in source_lock


def test_case_pack_report_preserves_boundary_labels(tmp_path: Path) -> None:
    pack_root = tmp_path / "case_packs"
    _write_case_pack(pack_root, scenario_id="case_a")
    output_dir = tmp_path / "out"

    assert main(
        [
            "pia-validate",
            "--case-pack-root",
            str(pack_root),
            "--output-dir",
            str(output_dir),
            "--strict-evidence",
        ]
    ) == 0

    report = (output_dir / "publication_report.md").read_text(encoding="utf-8")
    checklist = (output_dir / "publication_claim_boundary_checklist.md").read_text(encoding="utf-8")
    assert "data_source = real_simulation_csv" in report
    assert "engineering_validity = simulation_only" in report
    assert "must_resimulate = true" in report
    assert "data_source = real_simulation_csv" in checklist
    assert "engineering_validity = simulation_only" in checklist
    assert "must_resimulate = true" in checklist
