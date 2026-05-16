import pytest

from goa_eval.parsers.mapping_parser import parse_mapping


def test_v8_mapping_records(tmp_path):
    extract_dir = pytest.importorskip("conftest").extract_fixture_zip("v8.zip", tmp_path)
    mapping = parse_mapping(extract_dir / "v8" / "8T1C_v8_netlist.mapping")

    assert mapping.instance_map["s1"] == "Xs1"
    assert mapping.instance_map["s8"] == "Xs8"
    assert mapping.node_map["o1"] == "o1"
    assert mapping.node_map["GND!"] == "0"
    assert mapping.port_map["clk"] == 1
