from __future__ import annotations

from pathlib import Path
import json
import os
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
                "Keep data_source and engineering_validity boundaries explicit. Respond in Chinese Markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                "请读取以下 CircuitPilot 参数、指标、评分和候选项，给出下一轮仿真参数分析。"
                "输出应包含：关键问题、候选优先级、每个候选的工程理由、风险和复核项、下一轮仿真建议。\n\n"
                f"```json\n{compact_payload}\n```"
            ),
        },
    ]


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
    result = {
        "model": model,
        "boundary": payload["boundary"],
        "analysis": analysis,
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
    lines = [
        "# CircuitPilot DeepSeek 参数分析",
        "",
        f"- model: `{result['model']}`",
        f"- data_source: `{boundary.get('data_source')}`",
        f"- engineering_validity: `{boundary.get('engineering_validity')}`",
        "",
        "本分析仅基于仿真 CSV、结构化指标、规则推荐和候选参数表，不是实物测试结论，也不表示自动优化闭环已经完成。",
        "",
        "## Analysis",
        "",
        str(result["analysis"]).strip(),
        "",
    ]
    return "\n".join(lines)


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
