from pathlib import Path

import pandas as pd
import pytest

from goa_eval.empyrean.waveform_adapter import convert_empyrean_waveform_csv


def test_empyrean_waveform_with_time_and_v_columns(tmp_path: Path):
    source = tmp_path / "waveform.csv"
    pd.DataFrame({"TIME": [0.0, 1e-6], "v(o1)": [0.0, 6.0]}).to_csv(source, index=False)

    result = convert_empyrean_waveform_csv(source, tmp_path / "out")

    frame = pd.read_csv(result.normalized_waveform_path)
    assert list(frame.columns) == ["time", "o1"]
    assert Path(result.column_map_path).exists()
    assert result.signal_count == 1


def test_empyrean_waveform_with_lowercase_time_and_plain_nodes(tmp_path: Path):
    source = tmp_path / "waveform.csv"
    pd.DataFrame({"time": [0.0, 1e-6], "o1": [0.0, 6.0], "O2": [0.0, 5.5]}).to_csv(source, index=False)

    result = convert_empyrean_waveform_csv(source, tmp_path / "out")

    frame = pd.read_csv(result.normalized_waveform_path)
    assert list(frame.columns) == ["time", "o1", "o2"]


def test_empyrean_waveform_without_time_column_raises_clear_error(tmp_path: Path):
    source = tmp_path / "waveform.csv"
    pd.DataFrame({"o1": [0.0, 6.0]}).to_csv(source, index=False)

    with pytest.raises(ValueError, match="TIME/time/XVAL/xval"):
        convert_empyrean_waveform_csv(source, tmp_path / "out")
