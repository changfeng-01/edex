from __future__ import annotations

from pathlib import Path
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

import pandas as pd
import yaml


Transport = Callable[[str, dict[str, str], str, float], dict[str, Any]]


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key_env: str = "DEEPSEEK_API_KEY",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or _urllib_transport

    def analyze(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "deepseek-v4-pro",
        temperature: float = 0.2,
    ) -> tuple[str, dict[str, Any]]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is required to call DeepSeek API.")
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            },
            ensure_ascii=False,
        )
        response = self.transport(
            f"{self.base_url}/chat/completions",
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            body,
            self.timeout,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("DeepSeek response did not contain choices[0].message.content.") from exc
        return str(content), {"model": model, "usage": response.get("usage", {})}


def build_analysis_payload(
    *,
    summary_path: Path,
    score_path: Path | None = None,
    metrics_path: Path | None = None,
    candidates_path: Path | None = None,
    params_path: Path | None = None,
    max_metric_rows: int = 30,
    max_candidate_rows: int = 20,
) -> dict[str, Any]:
    summary = _read_json(summary_path)
    score = _read_json(score_path) if score_path else {}
    metric_rows = _read_csv_rows(metrics_path, max_metric_rows) if metrics_path else []
    candidate_rows = _read_csv_rows(candidates_path, max_candidate_rows) if candidates_path else []
    parameters = _read_yaml(params_path) if params_path else {}
    return {
        "boundary": {
            "data_source": summary.get("data_source", "real_simulation_csv"),
            "engineering_validity": summary.get("engineering_validity", "simulation_only"),
        },
        "summary": summary,
        "score": score,
        "metric_rows": metric_rows,
        "candidate_rows": candidate_rows,
        "parameters": parameters,
    }


def build_deepseek_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    compact_payload = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return [
        {
            "role": "system",
            "content": (
                "You are CircuitPilot's circuit-parameter analysis assistant. "
                "Analyze only the provided simulation CSV derived metrics and candidate parameters. "
                "Do not claim physical validation, silicon validation, or a completed automatic optimization loop. "
                "Return one JSON object only, without prose outside JSON. "
                "Required keys: key_issues, candidate_priorities, risk_checks, rerun_plan, boundary_statement. "
                "Keep data_source and engineering_validity boundaries explicit."
            ),
        },
        {
            "role": "user",
            "content": (
                "请读取以下 CircuitPilot 参数、指标、评分和候选项，给出下一轮仿真参数分析。"
                "返回 JSON：key_issues 为关键问题列表；candidate_priorities 为候选优先级列表；"
                "risk_checks 为风险和复核项；rerun_plan 为下一轮仿真建议；"
                "boundary_statement 必须包含 data_source 与 engineering_validity。\n\n"
                f"```json\n{compact_payload}\n```"
            ),
        },
    ]


def parse_structured_analysis(analysis: str) -> dict[str, Any]:
    text = str(analysis).strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_structured_analysis(structured: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    candidate_ids = {
        str(row.get("candidate_id"))
        for row in payload.get("candidate_rows", [])
        if isinstance(row, dict) and row.get("candidate_id") not in {None, ""}
    }
    known_metrics = _known_metric_names(payload)
    missing_candidate_ids = sorted(
        candidate_id for candidate_id in _referenced_candidate_ids(structured) if candidate_id not in candidate_ids
    )
    unknown_metrics = sorted(metric for metric in _referenced_metrics(structured) if metric not in known_metrics)
    boundary = payload.get("boundary", {})
    boundary_text = str(structured.get("boundary_statement", ""))
    expected_data_source = str(boundary.get("data_source", "real_simulation_csv"))
    expected_validity = str(boundary.get("engineering_validity", "simulation_only"))
    boundary_missing = expected_data_source not in boundary_text or expected_validity not in boundary_text
    forbidden_claims = _forbidden_claim_hits(json.dumps(structured, ensure_ascii=False, default=str))

    if not structured:
        warnings.append("DeepSeek response did not return structured JSON.")
    if missing_candidate_ids:
        warnings.append("DeepSeek response referenced candidate IDs that are not in next_candidates.csv.")
    if unknown_metrics:
        warnings.append("DeepSeek response referenced metrics that are not in the supplied inputs.")
    if boundary_missing:
        warnings.append("DeepSeek response did not repeat the required data_source and engineering_validity boundary.")
    if forbidden_claims:
        warnings.append("DeepSeek response contains forbidden overclaim wording.")

    return {
        "status": "warning" if warnings else "pass",
        "warnings": warnings,
        "missing_candidate_ids": missing_candidate_ids,
        "unknown_metrics": unknown_metrics,
        "boundary_missing": boundary_missing,
        "forbidden_claims": forbidden_claims,
    }


def run_llm_parameter_analysis(
    *,
    summary_path: Path,
    output_md: Path,
    output_json: Path,
    score_path: Path | None = None,
    metrics_path: Path | None = None,
    candidates_path: Path | None = None,
    params_path: Path | None = None,
    model: str = "deepseek-v4-pro",
    mock_response: str | None = None,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    payload = build_analysis_payload(
        summary_path=summary_path,
        score_path=score_path,
        metrics_path=metrics_path,
        candidates_path=candidates_path,
        params_path=params_path,
    )
    messages = build_deepseek_messages(payload)
    if mock_response is not None:
        analysis = mock_response
        metadata = {"model": model, "usage": {}, "mock_response": True}
    else:
        analysis, metadata = (client or DeepSeekClient()).analyze(messages=messages, model=model)
    structured_analysis = parse_structured_analysis(analysis)
    validation = validate_structured_analysis(structured_analysis, payload)
    result = {
        "model": model,
        "boundary": payload["boundary"],
        "analysis": analysis,
        "structured_analysis": structured_analysis,
        "validation": validation,
        "metadata": metadata,
        "input_files": {
            "summary": str(summary_path),
            "score": str(score_path) if score_path else None,
            "metrics": str(metrics_path) if metrics_path else None,
            "candidates": str(candidates_path) if candidates_path else None,
            "params": str(params_path) if params_path else None,
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    output_md.write_text(_analysis_markdown(result), encoding="utf-8")
    return result


def _analysis_markdown(result: dict[str, Any]) -> str:
    boundary = result["boundary"]
    structured = result.get("structured_analysis") or {}
    validation = result.get("validation") or {}
    lines = [
        "# CircuitPilot DeepSeek 参数分析",
        "",
        f"- model: `{result['model']}`",
        f"- data_source: `{boundary.get('data_source')}`",
        f"- engineering_validity: `{boundary.get('engineering_validity')}`",
        f"- validation_status: `{validation.get('status', 'unknown')}`",
        "",
        "本分析仅基于仿真 CSV、结构化指标、规则推荐和候选参数表；不是实物测试结论，也不表示自动优化闭环已经完成。",
        "",
    ]
    if structured:
        lines.extend(_structured_markdown_sections(structured, validation))
    else:
        lines.extend(
            [
                "## Validation",
                "",
                "- DeepSeek response was not structured JSON; raw analysis is shown below.",
                "",
            ]
        )
    lines.extend(["## Analysis", "", str(result["analysis"]).strip(), ""])
    return "\n".join(lines)


def _structured_markdown_sections(structured: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    lines = ["## Validation", ""]
    warnings = validation.get("warnings", [])
    if warnings:
        lines.extend(f"- WARNING: {warning}" for warning in warnings)
    else:
        lines.append("- Structured analysis passed local candidate, metric, and boundary checks.")
    lines.extend(["", "## Key Issues", ""])
    lines.extend(_items_markdown(structured.get("key_issues"), ["metric", "finding", "evidence"]))
    lines.extend(["", "## Candidate Priorities", ""])
    lines.extend(_items_markdown(structured.get("candidate_priorities"), ["candidate_id", "priority", "reason", "risk"]))
    lines.extend(["", "## Risk Checks", ""])
    lines.extend(_items_markdown(structured.get("risk_checks"), ["check", "metric", "reason"]))
    lines.extend(["", "## Rerun Plan", ""])
    lines.extend(_items_markdown(structured.get("rerun_plan"), []))
    lines.extend(["", "## Boundary Statement", "", str(structured.get("boundary_statement", "")).strip() or "N/A", ""])
    return lines


def _items_markdown(value: Any, preferred_keys: list[str]) -> list[str]:
    items = value if isinstance(value, list) else ([] if value in {None, ""} else [value])
    if not items:
        return ["- N/A"]
    lines = []
    for item in items:
        if isinstance(item, dict):
            keys = preferred_keys or list(item)
            parts = [f"{key}: {item[key]}" for key in keys if key in item and item[key] not in {None, ""}]
            lines.append("- " + "; ".join(parts or [json.dumps(item, ensure_ascii=False, default=str)]))
        else:
            lines.append(f"- {item}")
    return lines


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_csv_rows(path: Path | None, max_rows: int) -> list[dict[str, Any]]:
    if path is None:
        return []
    frame = pd.read_csv(path)
    frame = frame.where(pd.notna(frame), None)
    return frame.head(max_rows).to_dict(orient="records")


def _known_metric_names(payload: dict[str, Any]) -> set[str]:
    names = set()
    for section in ["summary", "score"]:
        value = payload.get(section, {})
        if isinstance(value, dict):
            names.update(str(key) for key in value)
    for row in payload.get("metric_rows", []):
        if isinstance(row, dict):
            names.update(str(key) for key in row)
    return names


def _referenced_candidate_ids(structured: dict[str, Any]) -> set[str]:
    ids = set()
    for item in structured.get("candidate_priorities", []) if isinstance(structured, dict) else []:
        if isinstance(item, dict) and item.get("candidate_id") not in {None, ""}:
            ids.add(str(item["candidate_id"]))
    return ids


def _referenced_metrics(structured: dict[str, Any]) -> set[str]:
    metrics = set()
    for key in ["key_issues", "risk_checks"]:
        for item in structured.get(key, []) if isinstance(structured, dict) else []:
            if isinstance(item, dict) and item.get("metric") not in {None, ""}:
                metrics.add(str(item["metric"]))
    return metrics


def _forbidden_claim_hits(text: str) -> list[str]:
    forbidden = [
        "silicon_verified",
        "validated_gain",
        "real_improvement",
        "physical validation passed",
        "物理验证通过",
        "芯片验证通过",
        "已完成自动优化闭环",
        "已验证优化完成",
    ]
    lowered = text.lower()
    return [phrase for phrase in forbidden if phrase.lower() in lowered]


def _urllib_transport(url: str, headers: dict[str, str], body: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc
