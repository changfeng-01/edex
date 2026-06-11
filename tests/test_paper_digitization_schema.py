from pathlib import Path

import pandas as pd
import yaml

from goa_eval.paper_digitization.build_case import build_paper_case
from goa_eval.paper_digitization.init_paper_db import initialize_paper_database


def test_init_paper_db_writes_verified_metadata_templates(tmp_path: Path):
    initialize_paper_database(tmp_path)

    metadata_path = tmp_path / "papers" / "you2024_10t2c_scan_driver" / "paper_metadata.yaml"
    plan_path = tmp_path / "papers" / "you2024_10t2c_scan_driver" / "extraction_plan.yaml"
    params_long = tmp_path / "data" / "paper_database" / "paper_params_long.csv"

    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))

    assert metadata["doi"] == "10.3390/electronics13122254"
    assert metadata["claim_boundary"] == "literature_extraction_only"
    assert plan["targets"][0]["status"] == "pending"
    assert "normalized_value" in pd.read_csv(params_long).columns


def test_paper_case_metadata_boundary(tmp_path: Path):
    waveform = tmp_path / "waveform.csv"
    waveform.write_text("time,o1\n0,0\n0.000001,6\n0.000004,6\n0.000005,0\n", encoding="utf-8")
    config = tmp_path / "case_config.yaml"
    config.write_text(
        f"""
case_id: you2024_fig9_stage18_19
paper_id: you2024_10t2c_scan_driver
figure_id: fig9
topology_id: GOA_10T2C_MOx
waveform_path: "{waveform.as_posix()}"
manual_digitization_required: true
""",
        encoding="utf-8",
    )

    case_dir = build_paper_case(case_config_path=config, output_root=tmp_path / "cases")
    metadata = yaml.safe_load((case_dir / "simulation_metadata.yaml").read_text(encoding="utf-8"))

    assert metadata["source_type"] == "paper_digitized"
    assert metadata["weak_label"] is True
    assert metadata["engineering_validity"] == "simulation_only"
