from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goa_eval.multi_agent.graph_app import run_multi_agent_task


def run_benchmark_suite(suite_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    suite = Path(suite_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    results = []
    for case_dir in _case_dirs(suite):
        task_path = case_dir / "task.yaml"
        expected = _load_expected(case_dir / "expected.json")
        case_output = output / "cases" / case_dir.name
        final_state = run_multi_agent_task(task_path, case_output)
        result = _case_result(case_dir, case_output, final_state, expected)
        results.append(result)

    summary = _summary(results)
    (output / "benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "case_results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    _write_report(output / "benchmark_report.md", summary, results)
    return summary


def _case_dirs(suite: Path) -> list[Path]:
    if (suite / "task.yaml").exists():
        return [suite]
    return sorted(path for path in suite.iterdir() if path.is_dir() and (path / "task.yaml").exists())


def _load_expected(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _case_result(case_dir: Path, output_dir: Path, final_state: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    selected = final_state.get("selected_domain_agent")
    expected_agent = expected.get("selected_domain_agent")
    route_ok = expected_agent in {None, selected}
    boundary_ok = (
        final_state.get("data_source") == "real_simulation_csv"
        and final_state.get("engineering_validity") == "simulation_only"
    )
    artifact_results = {}
    evidence = final_state.get("evidence_index") or {}
    artifacts = evidence.get("artifacts") or {}
    for artifact in expected.get("required_artifacts", []):
        artifact_results[artifact] = bool((artifacts.get(artifact) or {}).get("exists"))
    forbidden_hits = _forbidden_hits(final_state, expected.get("forbidden_claims", []))
    return {
        "case_name": case_dir.name,
        "output_dir": str(output_dir),
        "selected_domain_agent": selected,
        "expected_domain_agent": expected_agent,
        "route_ok": route_ok,
        "boundary_ok": boundary_ok and not forbidden_hits,
        "required_artifacts": artifact_results,
        "forbidden_hits": forbidden_hits,
        "warning_count": len(final_state.get("warnings", [])),
        "failure_count": len(final_state.get("failures", [])),
        "data_source": final_state.get("data_source"),
        "engineering_validity": final_state.get("engineering_validity"),
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    case_count = len(results)
    route_count = sum(1 for result in results if result["route_ok"])
    boundary_count = sum(1 for result in results if result["boundary_ok"])
    return {
        "schema_version": "1.0",
        "result_version": "1.0",
        "case_count": case_count,
        "metrics": {
            "route_accuracy": route_count / case_count if case_count else 0.0,
            "boundary_safety_score": boundary_count / case_count if case_count else 0.0,
        },
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }


def _forbidden_hits(final_state: dict[str, Any], forbidden_claims: list[str]) -> list[str]:
    haystack = json.dumps(
        {
            "agent_messages": final_state.get("agent_messages", []),
            "warnings": final_state.get("warnings", []),
            "failures": final_state.get("failures", []),
        },
        ensure_ascii=False,
    ).lower()
    return [claim for claim in forbidden_claims if str(claim).lower() in haystack]


def _write_report(path: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    lines = [
        "# Multi-Agent Benchmark Report",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Route accuracy: {summary['metrics']['route_accuracy']:.3f}",
        f"- Boundary safety score: {summary['metrics']['boundary_safety_score']:.3f}",
        "- Data source: real_simulation_csv",
        "- Engineering validity: simulation_only",
        "",
        "## Cases",
    ]
    for result in results:
        lines.append(
            f"- {result['case_name']}: route_ok={result['route_ok']}, boundary_ok={result['boundary_ok']}, "
            f"agent={result['selected_domain_agent']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
