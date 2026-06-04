import json
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.llm_analysis import (
    DeepSeekClient,
    build_analysis_payload,
    parse_structured_analysis,
    run_llm_parameter_analysis,
    validate_structured_analysis,
)


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    summary = tmp_path / "real_summary.json"
    score = tmp_path / "score_summary.json"
    metrics = tmp_path / "real_metrics.csv"
    candidates = tmp_path / "next_candidates.csv"
    params = tmp_path / "params.yaml"

    summary.write_text(
        json.dumps(
            {
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "Overall_status": "FAIL",
                "Max_ripple": 1.2,
                "Delay_mean": 1.4e-5,
            }
        ),
        encoding="utf-8",
    )
    score.write_text(
        json.dumps(
            {
                "hard_constraint_passed": False,
                "overall_score": 72.5,
                "failure_reasons": ["Max_ripple exceeds threshold"],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {"stage": 1, "node": "o1", "Ripple": 1.2, "Delay": 1.4e-5},
            {"stage": 2, "node": "o2", "Ripple": 0.8, "Delay": 1.5e-5},
        ]
    ).to_csv(metrics, index=False)
    pd.DataFrame(
        [
            {
                "candidate_id": "cand_001",
                "parameter": "capacitance",
                "direction": "increase",
                "candidate_value": 1.2e-12,
                "candidate_unit": "F",
                "search_score": 90,
                "parameters_json": '{"capacitance": 1.2e-12}',
            }
        ]
    ).to_csv(candidates, index=False)
    params.write_text(
        """
run_id: run_001
parameters:
  capacitance: 1.0e-12
  drive_resistance: 1500
conditions:
  temp: 25
  corner: tt
""".strip(),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "score": score,
        "metrics": metrics,
        "candidates": candidates,
        "params": params,
    }


def test_build_analysis_payload_reads_boundary_metrics_candidates_and_params(tmp_path):
    paths = _write_inputs(tmp_path)

    payload = build_analysis_payload(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        candidates_path=paths["candidates"],
        params_path=paths["params"],
    )

    assert payload["boundary"] == {
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
    }
    assert payload["summary"]["Overall_status"] == "FAIL"
    assert payload["score"]["overall_score"] == 72.5
    assert payload["metric_rows"][0]["node"] == "o1"
    assert payload["candidate_rows"][0]["candidate_id"] == "cand_001"
    assert payload["parameters"]["parameters"]["capacitance"] == 1.0e-12


def test_deepseek_client_posts_openai_compatible_payload(monkeypatch):
    captured = {}

    def fake_transport(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "content": "优先增加保持电容，并复核延迟。"
                    }
                }
            ],
            "usage": {"total_tokens": 123},
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = DeepSeekClient(transport=fake_transport)

    content, metadata = client.analyze(
        messages=[{"role": "user", "content": "Analyze parameters"}],
        model="deepseek-v4-pro",
    )

    assert content == "优先增加保持电容，并复核延迟。"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-v4-pro"
    assert captured["body"]["messages"][0]["content"] == "Analyze parameters"
    assert metadata["model"] == "deepseek-v4-pro"
    assert metadata["usage"]["total_tokens"] == 123


def test_deepseek_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = DeepSeekClient(transport=lambda *_args: {})

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        client.analyze(messages=[{"role": "user", "content": "x"}])


def test_run_llm_parameter_analysis_writes_markdown_and_json_with_mock_response(tmp_path):
    paths = _write_inputs(tmp_path)
    output_md = tmp_path / "llm_parameter_analysis.md"
    output_json = tmp_path / "llm_parameter_analysis.json"

    run_llm_parameter_analysis(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        candidates_path=paths["candidates"],
        params_path=paths["params"],
        output_md=output_md,
        output_json=output_json,
        model="deepseek-v4-pro",
        mock_response="建议优先跑 cand_001，并保持 simulation_only 边界。",
    )

    md = output_md.read_text(encoding="utf-8")
    data = json.loads(output_json.read_text(encoding="utf-8"))
    assert "deepseek-v4-pro" in md
    assert "simulation_only" in md
    assert "cand_001" in md
    assert data["model"] == "deepseek-v4-pro"
    assert data["boundary"]["engineering_validity"] == "simulation_only"
    assert "simulation_only" in data["analysis"]


def test_structured_deepseek_analysis_is_parsed_validated_and_rendered(tmp_path):
    paths = _write_inputs(tmp_path)
    output_md = tmp_path / "llm_parameter_analysis.md"
    output_json = tmp_path / "llm_parameter_analysis.json"
    response = json.dumps(
        {
            "key_issues": [
                {
                    "metric": "Max_ripple",
                    "finding": "Ripple exceeds threshold and drives candidate priority.",
                    "evidence": "score_summary.failure_reasons",
                }
            ],
            "candidate_priorities": [
                {
                    "candidate_id": "cand_001",
                    "priority": "high",
                    "reason": "Candidate directly targets Max_ripple.",
                    "risk": "must resimulate",
                }
            ],
            "risk_checks": [{"check": "review ripple and delay coupling", "metric": "Delay"}],
            "rerun_plan": ["rerun cand_001 and compare Max_ripple plus Delay"],
            "boundary_statement": "data_source = real_simulation_csv; engineering_validity = simulation_only",
        },
        ensure_ascii=False,
    )

    result = run_llm_parameter_analysis(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        candidates_path=paths["candidates"],
        params_path=paths["params"],
        output_md=output_md,
        output_json=output_json,
        model="deepseek-v4-pro",
        mock_response=response,
    )

    assert result["structured_analysis"]["candidate_priorities"][0]["candidate_id"] == "cand_001"
    assert result["validation"]["status"] == "pass"
    assert result["validation"]["missing_candidate_ids"] == []
    assert result["validation"]["unknown_metrics"] == []

    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["structured_analysis"]["key_issues"][0]["metric"] == "Max_ripple"
    md = output_md.read_text(encoding="utf-8")
    assert "## Key Issues" in md
    assert "cand_001" in md
    assert "engineering_validity = simulation_only" in md


def test_structured_deepseek_validation_flags_unknown_candidate_and_metric(tmp_path):
    paths = _write_inputs(tmp_path)
    payload = build_analysis_payload(
        summary_path=paths["summary"],
        score_path=paths["score"],
        metrics_path=paths["metrics"],
        candidates_path=paths["candidates"],
        params_path=paths["params"],
    )
    structured = {
        "key_issues": [{"metric": "NotARealMetric", "finding": "bad metric"}],
        "candidate_priorities": [{"candidate_id": "missing_candidate", "priority": "high", "reason": "bad id"}],
        "risk_checks": [],
        "rerun_plan": ["rerun"],
        "boundary_statement": "simulation_only",
    }

    validation = validate_structured_analysis(structured, payload)

    assert validation["status"] == "warning"
    assert validation["missing_candidate_ids"] == ["missing_candidate"]
    assert validation["unknown_metrics"] == ["NotARealMetric"]
    assert validation["boundary_missing"] is True


def test_parse_structured_analysis_accepts_json_fence():
    text = """```json
{"key_issues": [], "candidate_priorities": [], "risk_checks": [], "rerun_plan": [], "boundary_statement": "data_source = real_simulation_csv; engineering_validity = simulation_only"}
```"""

    parsed = parse_structured_analysis(text)

    assert parsed["boundary_statement"].startswith("data_source")
