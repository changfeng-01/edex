from pathlib import Path

import pandas as pd
import pytest

from goa_eval.paper_digitization.quality_check import run_quality_check
from goa_eval.paper_digitization.wpd_import import convert_wpd_csv


def test_wpd_import_two_column(tmp_path: Path):
    source = tmp_path / "wpd.csv"
    source.write_text("time_us,voltage_v\n0.0,-6.0\n0.1,-5.8\n", encoding="utf-8")
    output = tmp_path / "case" / "waveform.csv"

    quality = convert_wpd_csv(input_path=source, output_path=output, time_unit="us", voltage_unit="V")
    frame = pd.read_csv(output)

    assert list(frame.columns) == ["time", "o1"]
    assert frame.loc[1, "time"] == 0.1e-6
    assert quality["weak_label"] is True


def test_wpd_import_xy_format(tmp_path: Path):
    source = tmp_path / "wpd_xy.csv"
    source.write_text("X,Y\n0.0,-6.0\n100.0,-5.8\n", encoding="utf-8")
    output = tmp_path / "case" / "waveform.csv"

    convert_wpd_csv(input_path=source, output_path=output, time_unit="ns", voltage_unit="V")
    frame = pd.read_csv(output)

    assert list(frame.columns) == ["time", "o1"]
    assert frame.loc[1, "time"] == pytest.approx(100e-9)


def test_wpd_import_multi_curve(tmp_path: Path):
    source = tmp_path / "wpd_multi.csv"
    source.write_text(
        "curve,time_us,voltage_v\n"
        "G18,0.0,-6.0\n"
        "G18,0.1,-5.8\n"
        "G19,0.0,-6.0\n"
        "G19,0.2,-5.9\n",
        encoding="utf-8",
    )
    curve_map = tmp_path / "curve_map.yaml"
    curve_map.write_text("curve_map:\n  G18: o1\n  G19: o2\n", encoding="utf-8")
    output = tmp_path / "case" / "waveform.csv"

    quality = convert_wpd_csv(
        input_path=source,
        output_path=output,
        time_unit="us",
        voltage_unit="V",
        curve_map_path=curve_map,
    )
    frame = pd.read_csv(output)

    assert list(frame.columns) == ["time", "o1", "o2"]
    assert frame["o2"].notna().all()
    assert quality["interpolated"] is True


def test_quality_check_time_monotonic(tmp_path: Path):
    waveform = tmp_path / "waveform.csv"
    waveform.write_text("time,o1\n0,0\n0.000002,6\n0.000001,0\n", encoding="utf-8")

    result = run_quality_check(waveform_path=waveform, case_id="bad_time")

    assert result["quality_status"] in {"warning", "warning_voltage_out_of_range"}
    assert result["checks"]["time_monotonic"] is False
