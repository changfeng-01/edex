from pathlib import Path

from goa_eval.param_space import load_run_params, parse_engineering_value


def test_parse_engineering_value_supports_common_circuit_units():
    assert parse_engineering_value("1pF") == 1e-12
    assert parse_engineering_value("10k") == 10_000.0
    assert parse_engineering_value("2u") == 2e-6
    assert parse_engineering_value(15) == 15.0
    assert parse_engineering_value("TT") is None


def test_load_run_params_flattens_parameters_and_conditions(tmp_path: Path):
    path = tmp_path / "params.yaml"
    path.write_text(
        """
run_id: run_001
circuit_version: goa_8t1c_v1
parameters:
  C_store: 1pF
  R_driver: 10k
  W_pmos: 2u
  W_nmos: 1u
  VDD: 15
  load_cap: 5pF
conditions:
  temp: 25
  corner: TT
""".strip(),
        encoding="utf-8",
    )

    params = load_run_params(path)

    assert params.run_id == "run_001"
    assert params.circuit_version == "goa_8t1c_v1"
    assert params.parameters["C_store"] == "1pF"
    assert params.conditions["corner"] == "TT"
    assert params.numeric_parameters["C_store"] == 1e-12
    assert params.flat_record()["R_driver"] == "10k"
    assert params.flat_record()["corner"] == "TT"
