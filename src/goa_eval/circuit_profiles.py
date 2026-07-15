from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from goa_eval.parameter_semantics import load_parameter_semantics, semantic_tag_index
from goa_eval.topology_profiles import DEFAULT_PROFILE_PATH, load_eval_profiles
from goa_eval.units import normalize_numeric_fields, parse_unit_value


DEFAULT_CIRCUIT_PROFILE_PATH = Path("config/circuit_profiles.yaml")


def load_circuit_profiles(path: Path = DEFAULT_CIRCUIT_PROFILE_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return load_eval_profiles(DEFAULT_PROFILE_PATH)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = raw.get("profiles", raw)
    if not isinstance(profiles, dict):
        raise ValueError(f"{path} must contain a profiles mapping")
    loaded: dict[str, dict[str, Any]] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            raise ValueError(f"profile {name} must be a mapping")
        loaded[str(name)] = _normalize_profile(str(name), profile, path)
    if "default" not in loaded:
        loaded["default"] = {"name": "default", "aliases": [], "metrics": {}, "profile_source": str(path)}
    _validate_profile_collection(loaded)
    return loaded


def resolve_circuit_profile(name: str | None, profiles: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    profiles = profiles or load_circuit_profiles()
    wanted = _normalize(name or "default")
    for profile_name, profile in profiles.items():
        aliases = [_normalize(profile_name), *[_normalize(alias) for alias in profile.get("aliases", [])]]
        if wanted in aliases:
            return {"name": profile_name, **profile}
    default = profiles.get("default", {"name": "default", "metrics": {}})
    return {"name": "default", **default}


def validate_profile_references(*, profile_file: Path, semantics_file: Path | None = None) -> None:
    profiles = load_circuit_profiles(profile_file)
    semantics = load_parameter_semantics(semantics_file) if semantics_file else {"parameters": {}, "parameter_groups": {}}
    known_tags = set(semantic_tag_index(semantics))
    errors: list[str] = []
    for profile_name, profile in profiles.items():
        for metric, rules in (profile.get("candidate_rules", {}) or {}).items():
            if isinstance(rules, dict):
                rules = [rules]
            for index, rule in enumerate(rules or []):
                if not isinstance(rule, dict):
                    errors.append(f"{profile_name}.{metric}[{index}] must be a mapping")
                    continue
                for tag in rule.get("semantic_tags", []) or []:
                    if tag not in known_tags:
                        errors.append(f"{profile_name}.candidate_rules.{metric}[{index}] references unknown semantic tag: {tag}")
    if errors:
        raise ValueError("; ".join(errors))


def _normalize_profile(name: str, profile: dict[str, Any], source: Path) -> dict[str, Any]:
    normalized = dict(profile)
    metrics = {}
    for metric_name, rule in (profile.get("metrics", {}) or {}).items():
        if not isinstance(rule, dict):
            raise ValueError(f"{name}.metrics.{metric_name} must be a mapping")
        metrics[metric_name] = normalize_numeric_fields(rule, unit=rule.get("unit"))
    normalized["metrics"] = metrics
    normalized["profile_source"] = source.as_posix()
    return normalized


def _validate_profile_collection(profiles: dict[str, dict[str, Any]]) -> None:
    aliases: dict[str, str] = {}
    errors: list[str] = []
    for profile_name, profile in profiles.items():
        for alias in (profile_name, *(profile.get("aliases", []) or [])):
            normalized_alias = _normalize(alias)
            owner = aliases.get(normalized_alias)
            if owner is not None and owner != profile_name:
                errors.append(
                    f"duplicate circuit profile alias {normalized_alias!r}: {owner} and {profile_name}"
                )
            aliases[normalized_alias] = profile_name

        supported_analyses = {
            _normalize(analysis)
            for analysis in [
                *(profile.get("required_analyses", []) or []),
                *(profile.get("optional_analyses", []) or []),
            ]
        }
        for metric_name, rule in (profile.get("metrics", {}) or {}).items():
            source_analysis = _normalize(rule.get("source_analysis"))
            if source_analysis and source_analysis not in supported_analyses:
                errors.append(
                    f"{profile_name}.metrics.{metric_name} references unsupported analysis: {source_analysis}"
                )
            unit = rule.get("unit")
            for field in ("minimum", "maximum", "target", "tolerance"):
                raw_value = rule.get(field)
                if isinstance(raw_value, str) and parse_unit_value(raw_value, expected_unit=unit) is None:
                    errors.append(
                        f"{profile_name}.metrics.{metric_name}.{field} has incompatible value {raw_value!r} for unit {unit!r}"
                    )
        metric_names = set((profile.get("metrics", {}) or {}).keys())
        for metric_name in (profile.get("hard_constraints", {}) or {}):
            if metric_name not in metric_names:
                errors.append(f"{profile_name}.hard_constraints references unknown metric: {metric_name}")
        weights = ((profile.get("objective", {}) or {}).get("weights", {}) or {})
        for metric_name in weights:
            if metric_name not in metric_names:
                errors.append(f"{profile_name}.objective.weights references unknown metric: {metric_name}")
    if errors:
        raise ValueError("; ".join(errors))


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")
