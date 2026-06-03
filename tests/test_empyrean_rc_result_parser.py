from pathlib import Path

import pandas as pd

from goa_eval.empyrean.rc_result_parser import parse_rc_result


def test_rc_result_csv_summarizes_resistance_and_capacitance(tmp_path: Path):
    source = tmp_path / "rc_result.csv"
    pd.DataFrame(
        {
            "net": ["gate", "gate", "pixel"],
            "resistance_ohm": [1.0, 2.0, 10.0],
            "capacitance_f": [1e-12, 2e-12, 5e-12],
        }
    ).to_csv(source, index=False)

    summary = parse_rc_result(source, tmp_path / "parasitic_summary.json")

    assert summary["status"] == "passed"
    assert summary["has_rc_data"] is True
    assert summary["total_resistance"] == 13.0
    assert summary["total_capacitance"] == 8e-12
    assert summary["max_resistance"] == 10.0
    assert summary["max_capacitance"] == 5e-12
    assert summary["net_count"] == 2


def test_missing_rc_file_is_not_provided(tmp_path: Path):
    summary = parse_rc_result(None, tmp_path / "parasitic_summary.json")

    assert summary["status"] == "not_provided"
    assert summary["has_rc_data"] is False
