from goa_eval.units import parse_unit_value


def test_parse_unit_value_supports_engineering_units():
    assert parse_unit_value("5mW", expected_unit="W") == 0.005
    assert parse_unit_value("20MHz", expected_unit="Hz") == 20_000_000.0
    assert parse_unit_value("55deg", expected_unit="deg") == 55.0
    assert parse_unit_value("10uA", expected_unit="A") == 0.00001
    assert parse_unit_value("0.8um", expected_unit="um") == 0.8
    assert parse_unit_value("1pF", expected_unit="F") == 1.0e-12


def test_parse_unit_value_rejects_ambiguous_suffixes():
    assert parse_unit_value("5u", expected_unit="A") is None
    assert parse_unit_value("10m", expected_unit="W") is None
    assert parse_unit_value("20M", expected_unit="Hz") is None
