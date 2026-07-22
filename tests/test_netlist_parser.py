import json

import pytest

from goa_eval.netlist_structure import summarize_netlist_structure, write_netlist_structure
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


def test_ams_net_style_netlist_parses_sources_models_and_op(tmp_path):
    netlist = tmp_path / "amsnet_example.spice"
    netlist.write_text(
        "\n".join(
            [
                "M1 7 2 6 6 NMOS W=1u L=1u",
                "M2 8 1 6 6 NMOS W=1u L=1u",
                "I1 6 0 DC 1mA",
                "M4 7 7 VDD VDD PMOS W=1u L=1u",
                "M3 8 7 VDD VDD PMOS W=1u L=1u",
                "C1 0 8 1nF",
                ".MODEL NMOS NMOS (LEVEL=1 VTO=1 KP=1.0e-4 LAMBDA=0.02)",
                ".MODEL PMOS PMOS (LEVEL=1 VTO=-1 KP=1.0e-4 LAMBDA=0.02)",
                ".OP",
                ".END",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_netlist(netlist)

    assert len([device for device in parsed.devices if device.kind == "mos"]) == 4
    current = next(device for device in parsed.devices if device.kind == "current_source")
    assert current.nodes == ["6", "0"]
    assert current.params_si["dc_value"] == pytest.approx(1e-3)
    assert len([device for device in parsed.devices if device.kind == "capacitor"]) == 1
    assert parsed.models["NMOS"]["kind"] == "NMOS"
    assert parsed.models["PMOS"]["params_si"]["KP"] == pytest.approx(1.0e-4)
    assert parsed.analysis_directives[0]["directive"] == ".OP"


def test_foundry_xmos_devices_are_summarized_as_mos(tmp_path):
    netlist = tmp_path / "foundry_xmos.spice"
    netlist.write_text(
        "\n".join(
            [
                "XM1 out in 0 0 foundry_nfet W=0.8u L=0.15u",
                "XM2 out in vdd vdd foundry_pfet W=1.6u L=0.15u",
                "CLOAD out 0 5f",
                ".tran 20p 4n",
                ".end",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_netlist(netlist)
    summary = summarize_netlist_structure(parsed)

    mos = [device for device in parsed.devices if device.kind == "mos"]
    assert [device.name for device in mos] == ["XM1", "XM2"]
    assert mos[0].nodes == ["out", "in", "0", "0"]
    assert mos[0].model == "foundry_nfet"
    assert summary["scalar_features"]["mos_count"] == 2
    assert summary["scalar_features"]["transistor_width_sum"] == pytest.approx(2.4e-6)
    assert "W=0.8u" not in summary["node_degrees"]


def test_netlist_structure_summary_writes_scalar_features(tmp_path):
    netlist = tmp_path / "structure.spice"
    netlist.write_text(
        "\n".join(
            [
                "M1 out in vdd vdd PMOS W=2u L=1u",
                "M2 out in 0 0 NMOS W=1u L=1u",
                "R1 out load 10k",
                "C1 load 0 2pF",
                "VDD vdd 0 DC 1.8",
                "I1 load 0 DC 10uA",
                ".TRAN 1n 100n",
                ".DC VDD 0 1.8 0.1",
                ".END",
            ]
        ),
        encoding="utf-8",
    )
    parsed = parse_netlist(netlist)

    summary = summarize_netlist_structure(parsed)
    output = write_netlist_structure(tmp_path / "netlist_structure.json", parsed)

    assert summary["device_counts"]["mos"] == 2
    assert summary["device_counts"]["resistor"] == 1
    assert summary["device_counts"]["current_source"] == 1
    assert summary["node_count"] >= 5
    assert summary["scalar_features"]["transistor_width_sum"] == pytest.approx(3e-6)
    assert summary["scalar_features"]["capacitance_sum"] == pytest.approx(2e-12)
    assert {item["directive"] for item in summary["analysis_directives"]} == {".TRAN", ".DC"}
    assert json.loads((tmp_path / "netlist_structure.json").read_text(encoding="utf-8")) == output
