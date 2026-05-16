from pathlib import Path

from conftest import write_raw_fixture
from goa_eval.parsers.metric_table_parser import parse_metric_table


def test_metric_table_reads_16_metrics(tmp_path):
    raw = write_raw_fixture(tmp_path / "raw")
    specs = parse_metric_table(raw / "评价指标表.html")
    symbols = {spec.symbol for spec in specs}
    names = {spec.name for spec in specs}

    assert len(specs) == 16
    assert {"Seq", "Cost"}.issubset(symbols)
    assert {"有效脉冲存在性", "误触发", "输出高电平", "输出低电平"}.issubset(names)
    assert all(spec.metric_type for spec in specs)
