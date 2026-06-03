from pathlib import Path

from goa_eval.empyrean.pve_report_parser import parse_physical_verification_reports, parse_verification_report


def test_drc_passed_from_zero_errors(tmp_path: Path):
    report = tmp_path / "drc_report.txt"
    report.write_text("DRC Summary\nErrors: 0\nWarnings: 0\n", encoding="utf-8")

    result = parse_verification_report("drc", report)

    assert result.status == "passed"
    assert result.error_count == 0


def test_drc_failed_from_errors(tmp_path: Path):
    report = tmp_path / "drc_report.txt"
    report.write_text("DRC Summary\nErrors: 2\nWidth violations: 2\n", encoding="utf-8")

    result = parse_verification_report("drc", report)

    assert result.status == "failed"
    assert result.error_count == 2


def test_lvs_correct_is_passed(tmp_path: Path):
    report = tmp_path / "lvs_report.txt"
    report.write_text("LVS result: CORRECT\n", encoding="utf-8")

    result = parse_verification_report("lvs", report)

    assert result.status == "passed"


def test_erc_open_or_short_is_failed(tmp_path: Path):
    report = tmp_path / "erc_report.txt"
    report.write_text("ERC Summary\nOpen Circuits: 1\nShort Circuits: 0\n", encoding="utf-8")

    result = parse_verification_report("erc", report)

    assert result.status == "failed"
    assert "erc_open_or_short" in result.evidence


def test_missing_reports_are_not_provided(tmp_path: Path):
    output = tmp_path / "physical_verification_summary.json"

    summary = parse_physical_verification_reports({}, output)

    assert summary["drc"]["status"] == "not_provided"
    assert summary["lvs"]["status"] == "not_provided"
    assert summary["erc"]["status"] == "not_provided"
    assert output.exists()
