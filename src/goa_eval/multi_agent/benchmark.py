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
    report_forbidden_hits = _report_forbidden_hits(case_output=output_dir, forbidden_claims=expected.get("forbidden_claims", []))
    risk_types = _critic_risk_types(final_state)
    expected_risk_types = [str(item) for item in expected.get("expected_risk_types", [])]
    optimization_status = _optimization_loop_status(output_dir, final_state)
    expected_optimization_status = expected.get("optimization_loop_status")
    diagnosis_terms = [str(item).lower() for item in expected.get("diagnosis_terms", [])]
    diagnosis_text = json.dumps(final_state.get("domain_diagnosis", {}), ensure_ascii=False).lower()
    artifacts_ok = all(artifact_results.values()) if artifact_results else True
    optimization_status_ok = expected_optimization_status in {None, optimization_status}
    report_claims_ok = not report_forbidden_hits
    boundary_safety_ok = boundary_ok and not forbidden_hits and report_claims_ok
    hard_constraints = {
        "route_ok": route_ok,
        "required_artifacts_present": artifacts_ok,
        "boundary_preserved": boundary_ok,
        "forbidden_claims_absent": not forbidden_hits,
        "report_forbidden_claims_absent": report_claims_ok,
        "optimization_loop_status_matches": optimization_status_ok,
    }
    hard_constraint_passed = all(hard_constraints.values())
    case_status = "passed" if hard_constraint_passed else "failed"
    case_metrics = {
        "route_accuracy": 1.0 if route_ok else 0.0,
        "artifact_discovery_score": _artifact_score(artifact_results),
        "diagnosis_match_score": _term_score(diagnosis_text, diagnosis_terms),
        "critic_risk_detection_score": _risk_score(risk_types, expected_risk_types),
        "boundary_safety_score": 1.0 if boundary_safety_ok else 0.0,
        "optimization_loop_status_score": 1.0 if optimization_status_ok else 0.0,
        "report_forbidden_claim_score": 1.0 if report_claims_ok else 0.0,
    }
    return {
        "case_name": case_dir.name,
        "output_dir": str(output_dir),
        "case_status": case_status,
        "hard_constraint_passed": hard_constraint_passed,
        "hard_constraints": hard_constraints,
        "selected_domain_agent": selected,
        "expected_domain_agent": expected_agent,
        "route_ok": route_ok,
        "boundary_ok": boundary_safety_ok,
        "required_artifacts": artifact_results,
        "forbidden_hits": forbidden_hits,
        "report_forbidden_hits": report_forbidden_hits,
        "critic_risk_types": risk_types,
        "expected_risk_types": expected_risk_types,
        "optimization_loop_status": optimization_status,
        "expected_optimization_loop_status": expected_optimization_status,
        "metrics": case_metrics,
        "warning_count": len(final_state.get("warnings", [])),
        "failure_count": len(final_state.get("failures", [])),
        "data_source": final_state.get("data_source"),
        "engineering_validity": final_state.get("engineering_validity"),
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    case_count = len(results)
    metric_names = [
        "route_accuracy",
        "artifact_discovery_score",
        "diagnosis_match_score",
        "critic_risk_detection_score",
        "boundary_safety_score",
        "optimization_loop_status_score",
        "report_forbidden_claim_score",
    ]
    status_counts = _status_counts(results)
    return {
        "schema_version": "1.0",
        "result_version": "1.0",
        "case_count": case_count,
        "status_counts": status_counts,
        "not_evaluable_count": status_counts.get("not_evaluable", 0),
        "hard_constraint_pass_rate": _hard_constraint_pass_rate(results),
        "metrics": {name: _average(results, name) for name in metric_names},
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


def _report_forbidden_hits(case_output: Path, forbidden_claims: list[str]) -> list[str]:
    report_path = case_output / "multi_agent_decision_report.md"
    if not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8", errors="replace").lower()
    hits = []
    for claim in forbidden_claims:
        phrase = str(claim).lower()
        index = text.find(phrase)
        context = text[max(0, index - 40) : index] if index >= 0 else ""
        sentence_start = text.rfind("\n", 0, index) if index >= 0 else -1
        sentence_context = text[max(0, sentence_start + 1) : index] if index >= 0 else ""
        if (
            index >= 0
            and "not" not in context
            and "must not" not in sentence_context
            and "forbidden phrase" not in context
            and "overclaim" not in context
        ):
            hits.append(claim)
    return hits


def _critic_risk_types(final_state: dict[str, Any]) -> list[str]:
    risks = [risk for verdict in final_state.get("critic_verdicts", []) for risk in verdict.get("risks", [])]
    return sorted({str(risk.get("risk_type")) for risk in risks if risk.get("risk_type")})


def _optimization_loop_status(output_dir: Path, final_state: dict[str, Any]) -> str | None:
    path = output_dir / "optimization_loop_record.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("status")
        except json.JSONDecodeError:
            return None
    candidate_status = (final_state.get("candidate_summary") or {}).get("status")
    return str(candidate_status) if candidate_status else None


def _artifact_score(artifact_results: dict[str, bool]) -> float:
    if not artifact_results:
        return 1.0
    return sum(1 for value in artifact_results.values() if value) / len(artifact_results)


def _term_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    return sum(1 for term in terms if term in text) / len(terms)


def _risk_score(actual: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    actual_set = set(actual)
    return sum(1 for risk in expected if risk in actual_set) / len(expected)


def _average(results: list[dict[str, Any]], metric_name: str) -> float:
    if not results:
        return 0.0
    return sum(float((result.get("metrics") or {}).get(metric_name, 0.0)) for result in results) / len(results)


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("case_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _hard_constraint_pass_rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(1 for result in results if result.get("hard_constraint_passed") is True) / len(results)


def _write_report(path: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    lines = [
        "# Multi-Agent Benchmark Report",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Hard constraint pass rate: {summary['hard_constraint_pass_rate']:.3f}",
        f"- Status counts: {summary['status_counts']}",
        *[f"- {name}: {value:.3f}" for name, value in summary["metrics"].items()],
        "- Data source: real_simulation_csv",
        "- Engineering validity: simulation_only",
        "",
        "## Cases",
        "",
        "| case | status | hard_constraints | route_ok | boundary_ok | artifact_score | optimization_status | agent |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(result["case_name"]),
                    str(result.get("case_status", "")),
                    str(result.get("hard_constraint_passed", "")),
                    str(result["route_ok"]),
                    str(result["boundary_ok"]),
                    f"{(result.get('metrics') or {}).get('artifact_discovery_score', 0.0):.3f}",
                    str(result.get("optimization_loop_status", "")),
                    str(result["selected_domain_agent"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
