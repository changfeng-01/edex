import pytest

from goa_eval.parsers.waveform_parser import read_waveform_csv


def test_read_waveform_csv_accepts_external_output_csv(tmp_path):
    waveform = tmp_path / "sample_waveform.csv"
    waveform.write_text(
        "\n".join(
            [
                "XVAL,v(stv),v(clk),v(clkb),v(o1),v(o2),v(o3),v(o4),v(o5),v(o6),v(o7),v(o8)",
                "0.0,0,0,15,0,0,0,0,0,0,0,0",
                "0.000001,0,15,0,6,0,0,0,0,0,0,0",
                "0.000002,0,15,0,0,6,0,0,0,0,0,0",
                "0.000003,0,15,0,0,0,6,0,0,0,0,0",
            ]
        ),
        encoding="utf-8",
    )

    bundle = read_waveform_csv(waveform, "v8")

    assert bundle.data_source == "simulation"
    assert bundle.engineering_validity == "simulation_result"
    assert len(bundle.time) == 4
    assert bundle.time[0] == pytest.approx(0.0)
    assert bundle.time[-1] == pytest.approx(3.0e-6)
    assert {"stv", "clk", "clkb", "o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8"} <= set(bundle.signals)


def test_read_waveform_csv_accepts_internal_space_delimited_csv(tmp_path):
    waveform = tmp_path / "internal_waveform.txt"
    waveform.write_text(
        "\n".join(
            [
                "TIME v(o1) v(o4) v(o8) v(net50) v(xs1.pu)",
                "0.0 0 0 0 0 0",
                "0.000001 6 0 0 1 4",
                "0.000002 0 6 0 2 3",
            ]
        ),
        encoding="utf-8",
    )

    bundle = read_waveform_csv(waveform, "v8")

    assert bundle.data_source == "simulation"
    assert bundle.engineering_validity == "simulation_result"
    assert len(bundle.time) == 3
    assert {"o1", "o4", "o8", "net50"} <= set(bundle.signals)
    assert "xs1.pu" in bundle.metadata["internal_nodes"]
    assert "xs1.pu" not in bundle.signals
