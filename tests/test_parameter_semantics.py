from pathlib import Path

from goa_eval.parameter_semantics import (
    affected_parameters_for_rule,
    load_parameter_semantics,
    semantic_tag_index,
)


def test_load_parameter_semantics_keeps_values_and_group_constraints():
    semantics = load_parameter_semantics(Path("config/parameter_semantics.yaml"))

    assert semantics["parameters"]["m1_width"]["unit"] == "um"
    assert semantics["parameters"]["m1_width"]["values"] == ["0.8um", "1.0um", "1.2um"]
    assert semantics["parameter_groups"]["input_pair"]["constraint"] == "must_change_together"


def test_semantic_tag_index_maps_tags_to_parameter_names():
    semantics = load_parameter_semantics(Path("config/parameter_semantics.yaml"))

    index = semantic_tag_index(semantics)

    assert {"m1_width", "m2_width"} <= set(index["input_pair_width"])
    assert "ibias" in index["bias_current"]


def test_affected_parameters_for_rule_expands_matching_group():
    semantics = load_parameter_semantics(Path("config/parameter_semantics.yaml"))

    matches = affected_parameters_for_rule(
        {"semantic_tags": ["input_pair_width"], "direction": "increase"},
        semantics,
    )

    input_pair = next(match for match in matches if match["parameter_group"] == "input_pair")
    assert input_pair["affected_parameters"] == ["m1_width", "m2_width"]
    assert input_pair["risk_level"] == "medium"
    assert input_pair["requires_user_confirmation"] is True
    assert input_pair["must_resimulate"] is True
