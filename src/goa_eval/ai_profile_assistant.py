from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import yaml

from goa_eval.io_utils import write_json
from goa_eval.llm_analysis import DeepSeekClient


def build_profile_assistant_payload(
    *,
    description_path: Path,
    profile_file: Path | None = None,
    params_file: Path | None = None,
    metrics_file: Path | None = None,
    score_file: Path | None = None,
) -> dict[str, Any]:
    return {
        "boundary": {
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
        },
        "description": description_path.read_text(encoding="utf-8") if description_path.exists() else str(description_path),
        "existing_profiles": _read_yaml(profile_file),
        "parameter_semantics": _read_yaml(params_file),
        "metrics": _read_table_or_json(metrics_file),
        "score": _read_table_or_json(score_file),
        "instructions": [
            "Return auditable draft YAML content only; do not claim physical validation.",
            "Generated drafts must be validated before they are used for scoring.",
            "Keep data_source=real_simulation_csv and engineering_validity=simulation_only.",
        ],
    }


def build_profile_assistant_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    compact = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return [
        {
            "role": "system",
            "content": (
                "You are CircuitPilot's AI profile assistant. Produce auditable circuit profile and "
                "parameter semantics drafts from the provided simulation-only context. Do not claim "
                "silicon validation, lab validation, or a completed automatic optimization loop. "
                "Respond as JSON with profile_draft, parameter_semantics_draft, and analysis."
            ),
        },
        {"role": "user", "content": f"Build draft configuration from this context:\n```json\n{compact}\n```"},
    ]


def run_ai_profile_assistant(
    *,
    description_path: Path,
    output_dir: Path,
    profile_file: Path | None = None,
    params_file: Path | None = None,
    metrics_file: Path | None = None,
    score_file: Path | None = None,
    model: str = "deepseek-v4-pro",
    mock_response: str | None = None,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    payload = build_profile_assistant_payload(
        description_path=description_path,
        profile_file=profile_file,
        params_file=params_file,
        metrics_file=metrics_file,
        score_file=score_file,
    )
    messages = build_profile_assistant_messages(payload)
    if mock_response is not None:
        content = mock_response
        metadata = {"model": model, "usage": {}, "mock_response": True}
    else:
        content, metadata = (client or DeepSeekClient()).analyze(messages=messages, model=model)
    parsed = _parse_response(content)
    profile_draft = _draft_with_boundary(parsed.get("profile_draft") or _empty_profile_draft())
    semantics_draft = parsed.get("parameter_semantics_draft") or _empty_semantics_draft()
    analysis = str(parsed.get("analysis") or content)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "profile_draft.yaml").write_text(
        yaml.safe_dump(profile_draft, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (output_dir / "parameter_semantics_draft.yaml").write_text(
        yaml.safe_dump(semantics_draft, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    result = {
        "model": model,
        "boundary": payload["boundary"],
        "analysis": analysis,
        "metadata": metadata,
        "input_files": {
            "description": str(description_path),
            "profile_file": str(profile_file) if profile_file else None,
            "params_file": str(params_file) if params_file else None,
            "metrics_file": str(metrics_file) if metrics_file else None,
            "score_file": str(score_file) if score_file else None,
        },
        "draft_files": {
            "profile_draft": str(output_dir / "profile_draft.yaml"),
            "parameter_semantics_draft": str(output_dir / "parameter_semantics_draft.yaml"),
        },
    }
    write_json(output_dir / "ai_profile_assistant.json", result)
    (output_dir / "ai_profile_assistant.md").write_text(_assistant_markdown(result), encoding="utf-8")
    return result


def _parse_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"analysis": content}
    return parsed if isinstance(parsed, dict) else {"analysis": content}


def _draft_with_boundary(profile_draft: dict[str, Any]) -> dict[str, Any]:
    draft = dict(profile_draft)
    draft.setdefault("schema_version", "1.0")
    profiles = draft.setdefault("profiles", {})
    if isinstance(profiles, dict):
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            profile.setdefault("boundary", {})
            profile["boundary"].setdefault("data_source", "real_simulation_csv")
            profile["boundary"].setdefault("engineering_validity", "simulation_only")
            profile.setdefault("metrics", {})
            profile.setdefault("candidate_rules", {})
    return draft


def _empty_profile_draft() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "profiles": {
            "draft_default": {
                "aliases": [],
                "boundary": {"data_source": "real_simulation_csv", "engineering_validity": "simulation_only"},
                "metrics": {},
                "candidate_rules": {},
            }
        },
    }


def _empty_semantics_draft() -> dict[str, Any]:
    return {"schema_version": "1.0", "parameters": {}, "parameter_groups": {}}


def _assistant_markdown(result: dict[str, Any]) -> str:
    boundary = result["boundary"]
    return "\n".join(
        [
            "# CircuitPilot AI Profile Assistant",
            "",
            f"- model: `{result['model']}`",
            f"- data_source: `{boundary.get('data_source')}`",
            f"- engineering_validity: `{boundary.get('engineering_validity')}`",
            "",
            "The generated files are auditable drafts only. Validate them before using them for scoring.",
            "",
            "## Analysis",
            "",
            str(result["analysis"]).strip(),
            "",
            "## Draft Files",
            "",
            f"- `{result['draft_files']['profile_draft']}`",
            f"- `{result['draft_files']['parameter_semantics_draft']}`",
            "",
        ]
    )


def _read_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_table_or_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in {".yaml", ".yml"}:
        return _read_yaml(path)
    return {"path": str(path), "text_preview": path.read_text(encoding="utf-8", errors="replace")[:4000]}
