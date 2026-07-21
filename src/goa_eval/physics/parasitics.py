from __future__ import annotations

from collections.abc import Iterable, Mapping

from .contracts import ParasiticComponent, ResolvedParasitic


_UNIT_FACTORS = {
    "f": 1.0,
    "pf": 1.0e-12,
    "ff": 1.0e-15,
    "ohm": 1.0,
    "kohm": 1.0e3,
}

_SOURCE_STATUS = {
    "sidecar_observed": "observed",
    "row_observed": "physical",
    "empyrean_summary": "physical",
    "legacy": "proxy_fallback",
    "configured_proxy": "proxy_fallback",
}


def resolve_parasitic_components(
    components: Mapping[str, ParasiticComponent],
    *,
    required: Iterable[str],
) -> dict[str, ResolvedParasitic]:
    """Resolve every parasitic independently so partial evidence stays visible."""

    resolved: dict[str, ResolvedParasitic] = {}
    for name in required:
        component = components.get(name)
        if component is None:
            resolved[name] = ResolvedParasitic(0.0, "zero_fallback", "missing")
            continue
        factor = _UNIT_FACTORS.get(component.unit.strip().lower())
        if factor is None:
            resolved[name] = ResolvedParasitic(0.0, component.source, "missing")
            continue
        value = max(float(component.value) * factor, 0.0)
        resolved[name] = ResolvedParasitic(
            value, component.source, _SOURCE_STATUS.get(component.source, "proxy_fallback")
        )
    return resolved
