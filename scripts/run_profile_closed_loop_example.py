from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goa_eval.optimizer import constrained_random_candidates, load_param_space, write_candidate_outputs
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations, write_recommendations_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a profile-aware candidate-generation closed-loop example.")
    parser.add_argument("--output-dir", default="outputs/profile_closed_loop_example")
    parser.add_argument("--waveform", default="examples/sample_waveform.csv")
    parser.add_argument("--param-space", default="examples/profile_closed_loop_params.yaml")
    parser.add_argument("--spec", default="config/spec.yaml")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    waveform_path = output_dir / "waveform.csv"
    shutil.copyfile(Path(args.waveform), waveform_path)
    _write_companion_metrics(output_dir)

    run_real_waveform_evaluation(
        waveform_path=waveform_path,
        internal_waveform_path=None,
        output_dir=output_dir,
        spec_path=Path(args.spec),
        topology="two_stage_opamp",
    )
    write_recommendations_markdown(
        summary_path=output_dir / "real_summary.json",
        score_path=output_dir / "score_summary.json",
        metrics_path=output_dir / "real_metrics.csv",
        output_path=output_dir / "recommendations.md",
    )

    summary = json.loads((output_dir / "real_summary.json").read_text(encoding="utf-8"))
    score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
    metrics = pd.read_csv(output_dir / "real_metrics.csv")
    recommendations = build_recommendations(summary, score, metrics)
    candidates = constrained_random_candidates(
        load_param_space(Path(args.param_space)),
        recommendations,
        max_candidates=args.max_candidates,
        seed=args.seed,
    )
    write_candidate_outputs(
        candidates,
        csv_path=output_dir / "next_candidates.csv",
        markdown_path=output_dir / "next_candidates.md",
    )
    validation = _validate_closed_loop(output_dir)
    (output_dir / "closed_loop_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Profile closed-loop example written to {output_dir}")
    print(f"profile={validation['topology_profile']} candidates={validation['candidate_count']}")
    return 0


def _write_companion_metrics(output_dir: Path) -> None:
    pd.DataFrame(
        [
            {"metric": "supply_voltage_v", "value": 1.8},
            {"metric": "supply_current_a", "value": 0.008},
        ]
    ).to_csv(output_dir / "op_metrics.csv", index=False)
    pd.DataFrame(
        {
            "frequency_hz": [1.0, 1.0e3, 1.0e6, 1.0e7],
            "gain_db": [30.0, 28.0, 20.0, -3.0],
        }
    ).to_csv(output_dir / "ac_metrics.csv", index=False)
    pd.DataFrame(
        {
            "input_v": [0.0, 0.9, 1.8],
            "output_v": [0.05, 0.8, 1.7],
        }
    ).to_csv(output_dir / "dc_metrics.csv", index=False)
    pd.DataFrame(
        {
            "TIME": [0.0, 1.0e-9, 2.0e-9, 3.0e-9, 4.0e-9],
            "v(out)": [0.0, 0.2, 1.8, 1.6, 0.1],
        }
    ).to_csv(output_dir / "tran_metrics.csv", index=False)


def _validate_closed_loop(output_dir: Path) -> dict:
    score = json.loads((output_dir / "score_summary.json").read_text(encoding="utf-8"))
    candidates = pd.read_csv(output_dir / "next_candidates.csv")
    penalties = score.get("analysis_metric_penalties", {})
    profile_metrics = {"dc_gain_db", "static_power_w"}
    candidate_metrics = {str(metric) for metric in candidates.get("trigger_metric", [])}
    candidate_parameters = {str(parameter) for parameter in candidates.get("parameter", [])}
    profile_candidate_rows = candidates[candidates["trigger_metric"].astype(str).str.contains("dc_gain_db|static_power_w", regex=True)]
    validation = {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "topology_profile": score.get("topology_profile"),
        "analysis_metric_penalties": sorted(penalties),
        "candidate_count": int(len(candidates)),
        "profile_candidate_count": int(len(profile_candidate_rows)),
        "candidate_metrics": sorted(candidate_metrics),
        "candidate_parameters": sorted(candidate_parameters),
    }
    if validation["topology_profile"] != "ota":
        raise SystemExit("closed-loop validation failed: expected ota topology profile")
    if not profile_metrics <= set(penalties):
        raise SystemExit("closed-loop validation failed: missing expected profile penalties")
    if profile_candidate_rows.empty:
        raise SystemExit("closed-loop validation failed: no profile-driven candidates generated")
    return validation


if __name__ == "__main__":
    raise SystemExit(main())
