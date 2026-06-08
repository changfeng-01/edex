from __future__ import annotations

import argparse
from pathlib import Path
import json
from typing import Any

import pandas as pd

from goa_eval.eclipse_benchmark.loaders import iter_offline_run_dirs, load_history, load_optional_csv, load_optional_json
from goa_eval.eclipse_benchmark.metrics import compute_convergence_curve, compute_run_metrics
from goa_eval.eclipse_benchmark.reports import build_markdown_report
from goa_eval.eclipse_benchmark.scoring import build_algorithm_leaderboard, compute_eclipse_benchmark_score
from goa_eval.eclipse_benchmark.statistics import statistical_test_status
from goa_eval.io_utils import write_json


OUTPUT_FILES = [
    "eclipse_benchmark_summary.json",
    "eclipse_algorithm_leaderboard.csv",
    "eclipse_algorithm_runs.csv",
    "eclipse_convergence_curves.csv",
    "eclipse_candidate_selection_audit.csv",
    "eclipse_metric_audit.json",
    "eclipse_benchmark_report.md",
]


def run_offline_replay_benchmark(
    *,
    runs_root: Path,
    output_root: Path,
    score_threshold: float = 80.0,
    baseline: str = "random",
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    run_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    candidate_audit_rows: list[dict[str, Any]] = []
    metric_audit: dict[str, Any] = {"runs": [], "missing_optional_files": []}

    for algorithm, seed, run_dir in iter_offline_run_dirs(runs_root):
        history = load_history(run_dir)
        candidate_audit = load_optional_csv(run_dir, "candidate_audit.csv")
        attention_audit = load_optional_csv(run_dir, "attention_audit.csv")
        ledger = load_optional_json(run_dir, "ledger.json")
        if candidate_audit.empty:
            metric_audit["missing_optional_files"].append(str(run_dir / "candidate_audit.csv"))
        if attention_audit.empty:
            metric_audit["missing_optional_files"].append(str(run_dir / "attention_audit.csv"))
        if not ledger:
            metric_audit["missing_optional_files"].append(str(run_dir / "ledger.json"))
        metrics = compute_run_metrics(
            history,
            candidate_audit=candidate_audit,
            attention_audit=attention_audit,
            score_threshold=score_threshold,
        )
        metrics["eclipse_benchmark_score"] = compute_eclipse_benchmark_score(metrics)
        run_rows.append({"algorithm": algorithm, "seed": seed, "run_dir": str(run_dir), **metrics})
        curve = compute_convergence_curve(history)
        for row in curve.to_dict(orient="records"):
            curve_rows.append({"algorithm": algorithm, "seed": seed, **row})
        if not candidate_audit.empty:
            for row in candidate_audit.to_dict(orient="records"):
                candidate_audit_rows.append({"algorithm": algorithm, "seed": seed, **row})
        metric_audit["runs"].append(
            {
                "algorithm": algorithm,
                "seed": seed,
                "run_dir": str(run_dir),
                "candidate_audit_available": not candidate_audit.empty,
                "attention_audit_available": not attention_audit.empty,
                "ledger_available": bool(ledger),
            }
        )

    runs_frame = pd.DataFrame(run_rows)
    leaderboard = build_algorithm_leaderboard(runs_frame)
    curves_frame = pd.DataFrame(curve_rows)
    candidate_frame = pd.DataFrame(candidate_audit_rows)
    runs_frame.to_csv(output_root / "eclipse_algorithm_runs.csv", index=False, encoding="utf-8-sig")
    leaderboard.to_csv(output_root / "eclipse_algorithm_leaderboard.csv", index=False, encoding="utf-8-sig")
    curves_frame.to_csv(output_root / "eclipse_convergence_curves.csv", index=False, encoding="utf-8-sig")
    candidate_frame.to_csv(output_root / "eclipse_candidate_selection_audit.csv", index=False, encoding="utf-8-sig")
    metric_audit["statistical_tests"] = statistical_test_status()
    write_json(output_root / "eclipse_metric_audit.json", metric_audit)

    summary = {
        "schema_version": "1.0",
        "result_version": "1.0",
        "benchmark_type": "eclipse_model_benchmark",
        "task_type": "optimizer_algorithm_quality",
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "result_claim": "real_evaluation_metrics_only",
        "runs_root": str(runs_root),
        "score_threshold": float(score_threshold),
        "baseline": baseline,
        "algorithm_count": int(leaderboard["algorithm"].nunique()) if "algorithm" in leaderboard else 0,
        "run_count": int(len(runs_frame)),
        "output_files": OUTPUT_FILES,
        "primary_metrics": [
            "best_feasible_score",
            "normalized_convergence_auc",
            "fe_at_target_score",
            "hard_constraint_pass_rate",
            "not_evaluable_rate",
        ],
    }
    write_json(output_root / "eclipse_benchmark_summary.json", summary)
    (output_root / "eclipse_benchmark_report.md").write_text(
        build_markdown_report(summary=summary, leaderboard=leaderboard),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eclipse-benchmark")
    parser.add_argument("--runs-root", default="outputs/eclipse_runs")
    parser.add_argument("--output-root", default="outputs/eclipse_benchmark")
    parser.add_argument("--score-threshold", type=float, default=80.0)
    parser.add_argument("--baseline", default="random")
    args = parser.parse_args(argv)
    run_offline_replay_benchmark(
        runs_root=Path(args.runs_root),
        output_root=Path(args.output_root),
        score_threshold=args.score_threshold,
        baseline=args.baseline,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
