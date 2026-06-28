from __future__ import annotations

import json

import pandas as pd
import pytest

from goa_eval.cli import main
from goa_eval.pia_ca_llso.paper_baselines import (
    PAPER_BASELINE_STRATEGIES,
    build_reproduction_cards,
    select_paper_baseline,
)
from goa_eval.pia_ca_llso.paper_reproduction import run_paper_reproduction_benchmark
from goa_eval.pia_ca_llso.selector import select_candidates


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_id": "h1",
                "level_label": "L1",
                "overall_score": 94.0,
                "hard_constraint_passed": True,
                "pullup_w_l": 80.0,
                "pulldown_w_l": 70.0,
                "vgh_vth_margin": 2.4,
                "ron_pullup_cload_proxy": 0.35,
            },
            {
                "sample_id": "h2",
                "level_label": "L2",
                "overall_score": 72.0,
                "hard_constraint_passed": True,
                "pullup_w_l": 76.0,
                "pulldown_w_l": 66.0,
                "vgh_vth_margin": 1.4,
                "ron_pullup_cload_proxy": 0.75,
            },
            {
                "sample_id": "h3",
                "level_label": "L4",
                "overall_score": 25.0,
                "hard_constraint_passed": False,
                "pullup_w_l": 55.0,
                "pulldown_w_l": 52.0,
                "vgh_vth_margin": 0.1,
                "ron_pullup_cload_proxy": 2.8,
            },
            {
                "sample_id": "h4",
                "level_label": "L3",
                "overall_score": 48.0,
                "hard_constraint_passed": False,
                "pullup_w_l": 60.0,
                "pulldown_w_l": 58.0,
                "vgh_vth_margin": 0.5,
                "ron_pullup_cload_proxy": 1.8,
            },
        ]
    )


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": "c_good",
                "pullup_w_l": 79.0,
                "pulldown_w_l": 69.0,
                "vgh_vth_margin": 2.2,
                "ron_pullup_cload_proxy": 0.45,
            },
            {
                "candidate_id": "c_uncertain",
                "pullup_w_l": 67.0,
                "pulldown_w_l": 62.0,
                "vgh_vth_margin": 0.8,
                "ron_pullup_cload_proxy": 1.2,
            },
            {
                "candidate_id": "c_bad",
                "pullup_w_l": 54.0,
                "pulldown_w_l": 50.0,
                "vgh_vth_margin": 0.05,
                "ron_pullup_cload_proxy": 3.0,
            },
        ]
    )


def test_reproduction_cards_document_fidelity_and_omissions() -> None:
    cards = build_reproduction_cards()

    assert {card["paper_id"] for card in cards} == set(PAPER_BASELINE_STRATEGIES)
    for card in cards:
        assert card["fidelity_level"] == "faithful_goa_reimplementation"
        assert card["claim_boundary"] == "not_original_paper_benchmark_reproduction"
        assert card["reproduced_components"]
        assert card["omitted_components"]
        assert card["parameter_mapping"]


def test_paper_baselines_are_registered_and_emit_boundary_fields() -> None:
    for strategy in PAPER_BASELINE_STRATEGIES:
        result = select_candidates(_candidates(), _history(), strategy=strategy, top_k=2)

        assert result.model_report["strategy"] == strategy
        assert result.explanation_report["data_source"] == "real_simulation_csv"
        assert result.explanation_report["engineering_validity"] == "simulation_only"
        assert result.explanation_report["must_resimulate"] is True
        assert result.selected_candidates["paper_baseline_strategy"].eq(strategy).all()
        assert result.selected_candidates["must_resimulate"].eq(True).all()
        assert result.selected_candidates["engineering_validity"].eq("simulation_only").all()
        assert result.selected_candidates["data_source"].eq("real_simulation_csv").all()


def test_paper_baseline_rejects_result_leakage_columns() -> None:
    candidates = _candidates().assign(overall_score=[99.0, 10.0, 1.0])

    with pytest.raises(ValueError, match="result leakage"):
        select_paper_baseline(candidates, _history(), strategy="paper_ca_llso", top_k=2)


def test_paper_baselines_do_not_emit_pia_exclusive_columns() -> None:
    selected = select_paper_baseline(_candidates(), _history(), strategy="paper_ca_llso", top_k=2)

    forbidden = {
        "capm_distance_to_l1",
        "capm_barrier_score",
        "adaptive_capm_weights_json",
        "classifier_hybrid_score",
        "constraint_ledger_repair_json",
        "simulation_window",
    }
    assert forbidden.isdisjoint(selected.columns)


def test_paper_reproduction_benchmark_writes_fixed_artifacts(tmp_path) -> None:
    summary = run_paper_reproduction_benchmark(_history(), _candidates(), tmp_path, top_k=2)

    expected = {
        "paper_reproduction_cards.json",
        "paper_baseline_runs.csv",
        "paper_baseline_summary.csv",
        "paper_baseline_win_rates.csv",
        "paper_reproduction_report.md",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    assert summary["data_source"] == "real_simulation_csv"
    assert summary["engineering_validity"] == "simulation_only"
    cards = json.loads((tmp_path / "paper_reproduction_cards.json").read_text(encoding="utf-8"))
    assert len(cards) == 3


def test_pia_validate_smoke_runs_pia_full_and_paper_baselines(tmp_path) -> None:
    output_dir = tmp_path / "validate"

    assert main(
        [
            "pia-validate",
            "--protocol",
            "config/pia_ca_llso_validation_protocol.yaml",
            "--output-dir",
            str(output_dir),
            "--smoke",
        ]
    ) == 0

    runs = pd.read_csv(output_dir / "paper_baseline_runs.csv")
    assert {"classifier_level_hybrid", *PAPER_BASELINE_STRATEGIES}.issubset(set(runs["method"]))
    assert (output_dir / "paper_reproduction_report.md").exists()
