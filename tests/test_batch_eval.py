import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.batch_eval import run_batch_evaluation


def _write_run(root: Path, run_id: str, offset: float) -> None:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "params.yaml").write_text(
        f"""
run_id: {run_id}
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
    (run_dir / "waveform.csv").write_text(
        "\n".join(
            [
                "XVAL,v(o1),v(o2),v(o3)",
                f"0.000000,0,0,0",
                f"0.000001,{6 + offset},0,0",
                f"0.000002,{6 + offset},{6 + offset},0",
                f"0.000003,0,{6 + offset},{6 + offset}",
                f"0.000004,0,0,{6 + offset}",
                f"0.000005,0,0,0",
            ]
        ),
        encoding="utf-8",
    )


def test_run_batch_evaluation_writes_aggregate_outputs(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, "run_001", 0.0)
    _write_run(runs_dir, "run_002", 0.5)
    out = tmp_path / "outputs_batch"

    result = run_batch_evaluation(runs_dir=runs_dir, output_dir=out)

    assert result.run_count == 2
    for name in ["all_metrics.csv", "all_scores.csv", "leaderboard.csv", "recommendations.md"]:
        assert (out / name).exists()

    leaderboard = pd.read_csv(out / "leaderboard.csv")
    assert list(leaderboard["run_id"]) == ["run_001", "run_002"]
    assert {"overall_score", "hard_constraint_passed", "circuit_version", "C_store", "R_driver", "corner"} <= set(leaderboard.columns)

    metrics = pd.read_csv(out / "all_metrics.csv")
    assert {"run_id", "stage", "node", "C_store", "VDD"}.issubset(metrics.columns)

    scores = pd.read_csv(out / "all_scores.csv")
    assert {"run_id", "overall_score", "failure_reasons", "warning_reasons"}.issubset(scores.columns)

    text = (out / "recommendations.md").read_text(encoding="utf-8")
    assert "simulation_only" in text
    assert "run_001" in text
    assert "C_store" in text


def test_evaluate_batch_cli_keeps_existing_package_entrypoint(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir, "run_001", 0.0)
    out = tmp_path / "outputs_batch"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "evaluate-batch",
            "--runs-dir",
            str(runs_dir),
            "--output-dir",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads((out / "run_manifest_batch.json").read_text(encoding="utf-8"))["run_count"] == 1
    assert (out / "leaderboard.csv").exists()
