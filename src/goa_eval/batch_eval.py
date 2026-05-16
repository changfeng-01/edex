from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import pandas as pd

from goa_eval.param_space import RunParameters, load_run_params
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.recommendation import build_recommendations
from goa_eval.schemas import RESULT_VERSION, SCHEMA_VERSION


@dataclass(frozen=True)
class BatchRun:
    run_id: str
    path: Path
    waveform_path: Path | None
    params_path: Path | None = None


@dataclass(frozen=True)
class BatchEvaluationResult:
    run_count: int
    output_dir: Path
    all_metrics_path: Path
    all_scores_path: Path
    leaderboard_path: Path
    recommendations_path: Path


def discover_runs(root: Path) -> list[BatchRun]:
    if not root.exists():
        return []
    runs = []
    for path in sorted(item for item in root.iterdir() if item.is_dir() and item.name.startswith("run_")):
        waveform = path / "waveform.csv"
        params = path / "params.yaml"
        runs.append(
            BatchRun(
                run_id=path.name,
                path=path,
                waveform_path=waveform if waveform.exists() else None,
                params_path=params if params.exists() else None,
            )
        )
    return runs


def run_batch_evaluation(*, runs_dir: Path, output_dir: Path) -> BatchEvaluationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metric_frames: list[pd.DataFrame] = []
    score_rows: list[dict] = []
    leaderboard_rows: list[dict] = []
    recommendation_sections: list[str] = [
        "# CircuitPilot Batch Recommendations",
        "",
        f"- schema_version: `{SCHEMA_VERSION}`",
        f"- result_version: `{RESULT_VERSION}`",
        "- engineering_validity: `simulation_only`",
        "",
        "本报告基于仿真 CSV 的批量评价结果生成，不代表实物测试，也不表示已经完成全自动闭环仿真优化。",
        "",
    ]

    runs = [run for run in discover_runs(runs_dir) if run.waveform_path is not None]
    for run in runs:
        params = (
            load_run_params(run.params_path)
            if run.params_path
            else RunParameters(
                run_id=run.run_id,
                circuit_version=None,
                parameters={},
                conditions={},
                numeric_parameters={},
            )
        )
        run_id = params.run_id or run.run_id
        run_output = output_dir / "runs" / run_id
        run_real_waveform_evaluation(waveform_path=run.waveform_path, internal_waveform_path=None, output_dir=run_output)
        flat_params = params.flat_record()

        metrics = pd.read_csv(run_output / "real_metrics.csv")
        for key, value in flat_params.items():
            metrics[key] = value
        metrics["run_id"] = run_id
        all_metric_frames.append(metrics)

        score = json.loads((run_output / "score_summary.json").read_text(encoding="utf-8"))
        summary = json.loads((run_output / "real_summary.json").read_text(encoding="utf-8"))
        score_row = _flatten_score(run_id, score, flat_params)
        score_rows.append(score_row)
        leaderboard_rows.append(
            {
                "run_id": run_id,
                "circuit_version": flat_params.get("circuit_version"),
                "overall_score": score.get("overall_score"),
                "hard_constraint_passed": score.get("hard_constraint_passed"),
                "Overall_status": summary.get("Overall_status"),
                **{key: value for key, value in flat_params.items() if key not in {"run_id", "circuit_version"}},
            }
        )

        recommendations = build_recommendations(summary, score, metrics)
        recommendation_sections.extend(_run_recommendation_markdown(run_id, flat_params, recommendations))

    all_metrics = pd.concat(all_metric_frames, ignore_index=True) if all_metric_frames else pd.DataFrame()
    all_scores = pd.DataFrame(score_rows)
    leaderboard = pd.DataFrame(leaderboard_rows)
    if not leaderboard.empty:
        leaderboard = leaderboard.sort_values(["overall_score", "run_id"], ascending=[False, True], na_position="last")

    all_metrics_path = output_dir / "all_metrics.csv"
    all_scores_path = output_dir / "all_scores.csv"
    leaderboard_path = output_dir / "leaderboard.csv"
    recommendations_path = output_dir / "recommendations.md"
    all_metrics.to_csv(all_metrics_path, index=False, encoding="utf-8-sig")
    all_scores.to_csv(all_scores_path, index=False, encoding="utf-8-sig")
    leaderboard.to_csv(leaderboard_path, index=False, encoding="utf-8-sig")
    recommendations_path.write_text("\n".join(recommendation_sections), encoding="utf-8")
    (output_dir / "run_manifest_batch.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "result_version": RESULT_VERSION,
                "run_count": len(runs),
                "runs_dir": str(runs_dir),
                "output_dir": str(output_dir),
                "engineering_validity": "simulation_only",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return BatchEvaluationResult(
        len(runs),
        output_dir,
        all_metrics_path,
        all_scores_path,
        leaderboard_path,
        recommendations_path,
    )


def _flatten_score(run_id: str, score: dict, flat_params: dict) -> dict:
    return {
        "run_id": run_id,
        "overall_score": score.get("overall_score"),
        "hard_constraint_passed": score.get("hard_constraint_passed"),
        "failure_reasons": json.dumps(score.get("failure_reasons", score.get("hard_constraint_failures", [])), ensure_ascii=False),
        "warning_reasons": json.dumps(score.get("warning_reasons", []), ensure_ascii=False),
        "function_score": score.get("function_score"),
        "quality_score": score.get("quality_score"),
        "stability_score": score.get("stability_score"),
        "consistency_score": score.get("consistency_score"),
        "cost_score": score.get("cost_score"),
        **flat_params,
    }


def _run_recommendation_markdown(run_id: str, flat_params: dict, recommendations: list[dict]) -> list[str]:
    lines = [f"## {run_id}", ""]
    if flat_params:
        lines.extend(["### Parameters", ""])
        for key, value in flat_params.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    lines.extend(["### Recommendations", ""])
    for item in recommendations:
        lines.extend(
            [
                f"- `{item['recommendation_id']}` ({item['severity']}): {item['message']}",
                f"  - trigger_metric: `{item.get('trigger_metric')}`",
                f"  - current_value: `{item.get('current_value')}`",
                f"  - threshold: `{item.get('threshold')}`",
                f"  - possible_physical_causes: {item.get('possible_physical_causes')}",
                f"  - next_tuning_actions: {item.get('next_tuning_actions')}",
                f"  - needs_metric_review: `{item.get('needs_metric_review')}`",
            ]
        )
    lines.append("")
    return lines
