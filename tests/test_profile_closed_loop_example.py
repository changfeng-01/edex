import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_profile_closed_loop_example_writes_profile_driven_candidates(tmp_path):
    output_dir = tmp_path / "profile_closed_loop"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_profile_closed_loop_example.py",
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
    candidates = pd.read_csv(output_dir / "next_candidates.csv")

    assert score["topology_profile"] == "ota"
    assert {"dc_gain_db", "static_power_w"} <= set(score["analysis_metric_penalties"])
    assert {"m1_width", "m2_width", "load_cap", "ibias"} & set(candidates["parameter"])
    assert {"dc_gain_db", "static_power_w"} & set(candidates["trigger_metric"])
    assert set(candidates["engineering_validity"]) == {"simulation_only"}
    assert (output_dir / "closed_loop_validation.json").exists()
