from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_PARAMETER_SEMANTICS_PATH = Path("config/parameter_semantics.yaml")


def load_parameter_semantics(path: Path | None = DEFAULT_PARAMETER_SEMANTICS_PATH) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"parameters": {}, "parameter_groups": {}}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parameters = raw.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError(f"{path} parameters must be a mapping")
    groups = raw.get("parameter_groups", {})
    if not isinstance(groups, dict):
        raise ValueError(f"{path} parameter_groups must be a mapping")
    return {
        "schema_version": raw.get("schema_version", "1.0"),
        "parameters": {str(name): _normalize_parameter(config) for name, config in parameters.items()},
        "parameter_groups": {str(name): _normalize_group(config) for name, config in groups.items()},
    }


def semantic_tag_index(semantics: dict[str, Any]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for name, config in (semantics.get("parameters", {}) or {}).items():
        for tag in config.get("semantic_tags", []) or []:
            index.setdefault(str(tag), []).append(str(name))
    return {tag: sorted(set(names)) for tag, names in index.items()}


def affected_parameters_for_rule(rule: dict[str, Any], semantics: dict[str, Any]) -> list[dict[str, Any]]:
    tags = [str(tag) for tag in rule.get("semantic_tags", []) or []]
    if not tags:
        return []
    index = semantic_tag_index(semantics)
    matched_parameters = sorted({parameter for tag in tags for parameter in index.get(tag, [])})
    if not matched_parameters:
        return []
    matches = []
    used: set[str] = set()
    for group_name, group in (semantics.get("parameter_groups", {}) or {}).items():
        members = [member for member in group.get("members", []) if member in matched_parameters]
        if not members:
            continue
        if group.get("constraint") in {"must_change_together", "keep_ratio"}:
            affected = [member for member in group.get("members", []) if member in semantics.get("parameters", {})]
        else:
            affected = members
        used.update(affected)
        matches.append(_match_record(group_name, affected, tags, semantics, rule))
    for parameter in matched_parameters:
        if parameter not in used:
            matches.append(_match_record("", [parameter], tags, semantics, rule))
    return matches


def _match_record(group_name: str, parameters: list[str], tags: list[str], semantics: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    risk_tags = sorted(
        {
            str(tag)
            for parameter in parameters
            for tag in (semantics.get("parameters", {}).get(parameter, {}).get("risk_tags", []) or [])
        }
    )
    affected_metrics = sorted(
        {
            str(metric)
            for parameter in parameters
            for metric in (semantics.get("parameters", {}).get(parameter, {}).get("affects", []) or [])
        }
    )
    return {
        "parameter_group": group_name,
        "affected_parameters": parameters,
        "semantic_tags": sorted(set(tags)),
        "affected_metrics": affected_metrics,
        "risk_tags": risk_tags,
        "risk_level": _risk_level(risk_tags, len(parameters)),
        "expected_tradeoff": str(rule.get("expected_tradeoff") or rule.get("rationale") or ""),
        "requires_user_confirmation": True,
        "must_resimulate": True,
    }


def _risk_level(risk_tags: list[str], parameter_count: int) -> str:
    high_tags = {"power", "thermal", "stability", "matching"}
    if high_tags & set(risk_tags):
        return "high"
    if parameter_count > 1 or risk_tags:
        return "medium"
    return "low"


def _normalize_parameter(config: Any) -> dict[str, Any]:
    if isinstance(config, dict):
        values = config.get("values", [])
        normalized = dict(config)
        normalized["values"] = list(values) if isinstance(values, list) else [values]
        normalized["semantic_tags"] = [str(tag) for tag in normalized.get("semantic_tags", []) or []]
        normalized["affects"] = [str(metric) for metric in normalized.get("affects", []) or []]
        normalized["risk_tags"] = [str(tag) for tag in normalized.get("risk_tags", normalized.get("risk", [])) or []]
        return normalized
    values = list(config) if isinstance(config, list) else [config]
    return {"values": values, "semantic_tags": [], "affects": [], "risk_tags": []}


def _normalize_group(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {"members": [], "constraint": ""}
    group = dict(config)
    group["members"] = [str(member) for member in group.get("members", []) or []]
    return group
