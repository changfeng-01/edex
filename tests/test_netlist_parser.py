import pytest

from goa_eval.parsers.netlist_parser import parse_netlist, parse_numeric_with_unit


def test_parse_units():
    assert parse_numeric_with_unit("850u") == pytest.approx(850e-6)
    assert parse_numeric_with_unit("800f") == pytest.approx(800e-15)
    assert parse_numeric_with_unit("100n") == pytest.approx(100e-9)
    assert parse_numeric_with_unit("10MEG") == pytest.approx(10e6)


def test_v1_netlist_parses_mos_and_capacitor(tmp_path):
    extract_dir = pytest.importorskip("conftest").extract_fixture_zip("v1.zip", tmp_path)
    parsed = parse_netlist(extract_dir / "v1" / "8T1C.netlist")

    mos = [device for device in parsed.devices if device.kind == "mos"]
    caps = [device for device in parsed.devices if device.kind == "capacitor"]
    m7 = next(device for device in mos if device.name == "m7")
    cc0 = next(device for device in caps if device.name == "CC0")

    assert len(mos) == 8
    assert len(caps) == 1
    assert m7.params_si["W"] == pytest.approx(850e-6)
    assert cc0.params_si["C"] == pytest.approx(800e-15)
    assert m7.kind == "mos"
    assert cc0.kind == "capacitor"


def test_v8_subckt_instances_and_cascade(tmp_path):
    from goa_eval.parsers.mapping_parser import parse_mapping
    from goa_eval.parsers.design_parser import build_design_version

    extract_dir = pytest.importorskip("conftest").extract_fixture_zip("v8.zip", tmp_path)
    root = extract_dir / "v8"
    parsed = parse_netlist(root / "8T1C_v8.netlist")
    mapping = parse_mapping(root / "8T1C_v8_netlist.mapping")
    design = build_design_version("v8", root, parsed, mapping)

    instances = {device.name: device for device in parsed.devices if device.kind == "subckt_instance"}
    cascade_instances = {name for name in instances if name.startswith("Xs")}
    cascade_outputs = {instances[f"Xs{i}"].port_map["output"] for i in range(1, 9)}

    assert "sub_1_8T1C" in parsed.subckts
    assert cascade_instances == {f"Xs{i}" for i in range(1, 9)}
    assert cascade_outputs == {f"o{i}" for i in range(1, 9)}
    assert "Xdummy" in instances
    assert instances["Xs1"].port_map["output"] == "o1"
    assert instances["Xs8"].port_map["output"] == "o5"
    assert design.cascade_chain == ["o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8"]
