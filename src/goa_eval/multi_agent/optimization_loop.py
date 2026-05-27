from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def build_optimization_loop_record(state: dict[str, Any]) -> dict[str, Any]:
    inputs = state.get("inputs") or {}
    baseline_best = (state.get("leaderboard_summary") or {}).get("best_candidate", {})
    candidate_summary = state.get("candidate_summary") or {}
    rerun_paths = _rerun_paths(inputs)
    rerun_best = _best_from_leaderboard(rerun_paths.get("rerun_leaderboard"))
    comparison = _compare_candidates(baseline_best, rerun_best)
    status = "decision_ready" if rerun_best else "awaiting_rerun_results"
    return {
        "schema_version": "1.0",
        "result_version": "1.0",
        "task_name": state.get("task_name"),
        "task_type": state.get("task_type"),
        "profile": state.get("profile"),
        "status": status,
        "baseline": {
            "leaderboard_path": inputs.get("leaderboard"),
            "baseline_run_dir": inputs.get("baseline_run_dir"),
            "best_candidate": baseline_best,
        },
        "next_candidates": {
            "path": candidate_summary.get("next_candidates_path"),
            "candidate_count": int(candidate_summary.get("candidate_count") or 0),
            "candidate_summary": candidate_summary.get("candidate_summary", []),
        },
        "rerun_instruction": _rerun_instruction(state),
        "rerun_results": rerun_paths,
        "comparison": comparison,
        "decision": _decision(status, comparison, rerun_best),
        "critic_context": {
            "top_risks": _top_risks(state),
            "verdicts": state.get("critic_verdicts", []),
        },
        "data_source": state.get("data_source", "real_simulation_csv"),
        "engineering_validity": state.get("engineering_validity", "simulation_only"),
    }


def write_optimization_artifacts(output_dir: str | Path, state: dict[str, Any], critic_report: dict[str, Any] | None = None) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if critic_report:
        state = {**state, "critic_verdicts": critic_report.get("verdicts", state.get("critic_verdicts", []))}
    record = build_optimization_loop_record(state)
    record_path = output / "optimization_loop_record.json"
    card_path = output / "optimization_decision_card.md"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    card_path.write_text(_decision_card(record, critic_report or {}), encoding="utf-8")
    return {"optimization_loop_record": str(record_path), "optimization_decision_card": str(card_path)}


def _rerun_paths(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "rerun_run_dir": inputs.get("rerun_run_dir"),
        "rerun_leaderboard": inputs.get("rerun_leaderboard"),
        "rerun_score_summary": inputs.get("rerun_score_summary"),
        "rerun_real_metrics": inputs.get("rerun_real_metrics"),
    }


def _best_from_leaderboard(path_text: Any) -> dict[str, Any]:
    if not path_text:
        return {}
    path = Path(str(path_text))
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if frame.empty:
        return {}
    if "overall_score" in frame.columns:
        row = frame.sort_values("overall_score", ascending=False, na_position="last").iloc[0]
    else:
        row = frame.iloc[0]
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _compare_candidates(baseline: dict[str, Any], rerun: dict[str, Any]) -> dict[str, Any]:
    if not rerun:
        return {"available": False, "reason": "rerun results not provided"}
    baseline_score = _number(baseline.get("overall_score"))
    rerun_score = _number(rerun.get("overall_score"))
    score_delta = None
    if baseline_score is not None and rerun_score is not None:
        score_delta = round(rerun_score - baseline_score, 12)
    return {
        "available": True,
        "baseline_candidate_id": baseline.get("candidate_id") or baseline.get("run_id"),
        "rerun_candidate_id": rerun.get("candidate_id") or rerun.get("run_id"),
        "baseline_overall_score": baseline_score,
        "rerun_overall_score": rerun_score,
        "score_delta": score_delta,
    }


def _decision(status: str, comparison: dict[str, Any], rerun_best: dict[str, Any]) -> dict[str, Any]:
    if status != "decision_ready":
        return {
            "decision": "await_rerun_results",
            "reason": "next_candidates were generated but no rerun leaderboard/score/metrics artifacts were provided",
        }
    delta = comparison.get("score_delta")
    if delta is None:
        return {"decision": "review_required", "reason": "rerun results exist but score delta cannot be computed", "rerun_best": rerun_best}
    if delta > 0:
        return {"decision": "accept_rerun_candidate", "reason": f"rerun overall_score improved by {delta}", "rerun_best": rerun_best}
    return {"decision": "reject_rerun_candidate", "reason": f"rerun overall_score did not improve; delta={delta}", "rerun_best": rerun_best}


def _rerun_instruction(state: dict[str, Any]) -> dict[str, str]:
    output_dir = state.get("output_dir") or "outputs/multi_agent_rerun"
    task_name = state.get("task_name") or "multi_agent_task"
    return {
        "command": f"python -m goa_eval.cli multi-agent-run --task <task-with-rerun-results-for-{task_name}> --output-dir {output_dir}",
        "note": "Run the proposed next_candidates through the existing deterministic simulation/evaluation flow, then provide rerun_leaderboard, rerun_score_summary, or rerun_real_metrics in the task inputs.",
    }


def _top_risks(state: dict[str, Any]) -> list[dict[str, Any]]:
    risks = []
    for verdict in state.get("critic_verdicts", []):
        risks.append(
            {
                "verdict": verdict.get("verdict"),
                "risk_type": verdict.get("risk_type"),
                "severity": verdict.get("severity"),
                "issues": verdict.get("issues", []),
            }
        )
    return risks[:5]


def _decision_card(record: dict[str, Any], critic_report: dict[str, Any]) -> str:
    top_risks = critic_report.get("top_risks") or record.get("critic_context", {}).get("top_risks", [])
    lines = [
        "# Optimization Decision Evidence Card",
        "",
        "## goal",
        "",
        f"- task: `{record.get('task_name')}`",
        f"- objective: `{record.get('task_type')}`",
        "",
        "## baseline",
        "",
        f"- best_candidate: `{_short(record.get('baseline', {}).get('best_candidate', {}))}`",
        "",
        "## candidate",
        "",
        f"- next_candidates_path: `{record.get('next_candidates', {}).get('path')}`",
        f"- candidate_count: `{record.get('next_candidates', {}).get('candidate_count')}`",
        "",
        "## rerun status",
        "",
        f"- status: `{record.get('status')}`",
        f"- rerun_results: `{_short(record.get('rerun_results', {}))}`",
        "",
        "## comparison",
        "",
        f"- comparison: `{_short(record.get('comparison', {}))}`",
        "",
        "## top risks",
        "",
        f"- risks: `{_short(top_risks)}`",
        "",
        "## decision",
        "",
        f"- decision: `{_short(record.get('decision', {}))}`",
        "",
        "## boundary",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "",
        "## next step",
        "",
        f"- {_short(record.get('rerun_instruction', {}).get('note', 'continue simulation-only evaluation'))}",
    ]
    return "\n".join(lines) + "\n"


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _short(value: Any, limit: int = 500) -> str:
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."
