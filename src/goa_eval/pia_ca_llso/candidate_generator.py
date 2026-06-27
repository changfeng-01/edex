from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.physics_distance import CAPM_DEFAULT_CONFIG


def _parameter_specs(problem_spec: Any) -> list[Any]:
    return list(getattr(problem_spec, "parameter_specs", problem_spec.get("parameter_specs", [])))


def generate_random_candidates(problem_spec: Any, n: int) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(42)
    for idx in range(n):
        row = {"candidate_id": f"random_{idx}", "source": "random"}
        for spec in _parameter_specs(problem_spec):
            name = getattr(spec, "name", spec.get("name"))
            lower = float(getattr(spec, "lower", spec.get("lower", 0.0)) or 0.0)
            upper = float(getattr(spec, "upper", spec.get("upper", 1.0)) or 1.0)
            row[name] = float(rng.uniform(lower, upper))
        rows.append(row)
    return pd.DataFrame(rows)


def generate_initial_samples(problem_spec: Any, n: int, method: str = "lhs") -> pd.DataFrame:
    samples = generate_random_candidates(problem_spec, n)
    samples["source"] = method
    return samples


def generate_llso_candidates(history: pd.DataFrame, problem_spec: Any, n: int) -> pd.DataFrame:
    return generate_elite_mutation_candidates(history, problem_spec, n)


def generate_elite_mutation_candidates(history: pd.DataFrame, problem_spec: Any, n: int) -> pd.DataFrame:
    if history.empty:
        return generate_random_candidates(problem_spec, n)
    best = history.sort_values("overall_score", ascending=False).head(1).iloc[0]
    rows = []
    rng = np.random.default_rng(43)
    for idx in range(n):
        row = {"candidate_id": f"elite_mutation_{idx}", "source": "mutation"}
        for spec in _parameter_specs(problem_spec):
            name = getattr(spec, "name", spec.get("name"))
            lower = float(getattr(spec, "lower", spec.get("lower", 0.0)) or 0.0)
            upper = float(getattr(spec, "upper", spec.get("upper", 1.0)) or 1.0)
            center = float(best.get(name, (lower + upper) / 2))
            row[name] = float(np.clip(center + rng.normal(0, (upper - lower) * 0.05), lower, upper))
        rows.append(row)
    return pd.DataFrame(rows)


def generate_de_candidates(history: pd.DataFrame, problem_spec: Any, n: int) -> pd.DataFrame:
    samples = generate_random_candidates(problem_spec, n)
    samples["source"] = "de"
    return samples


def load_imported_candidates(candidate_csv: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(candidate_csv)
    if "candidate_id" not in frame.columns:
        frame.insert(0, "candidate_id", [f"candidate_{idx}" for idx in range(len(frame))])
    if "source" not in frame.columns:
        frame["source"] = "imported"
    return frame


def merge_and_deduplicate_candidates(candidates: list[pd.DataFrame] | pd.DataFrame) -> pd.DataFrame:
    frame = pd.concat(candidates, ignore_index=True) if isinstance(candidates, list) else candidates.copy()
    parameter_cols = [col for col in frame.columns if col not in {"candidate_id", "source"}]
    return frame.drop_duplicates(subset=parameter_cols, keep="first").reset_index(drop=True)


REPAIR_ACTIONS = {
    "vgh_vth_margin": [("VGH", "increase"), ("Vth_shift", "decrease")],
    "vgl_off_margin": [("VGL", "decrease"), ("Vth_shift", "decrease")],
    "cboot_cload_ratio": [("C_boot", "increase"), ("C_load", "decrease")],
    "ron_pullup_cload_proxy": [("TFT_pullup_W", "increase"), ("C_load", "decrease")],
    "ron_pulldown_cload_proxy": [("TFT_pulldown_W", "increase"), ("C_load", "decrease")],
    "clk_slew_proxy": [("CLK_rise_time", "decrease"), ("CLK_fall_time", "decrease")],
}


def generate_constraint_repair_candidates(
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    repair_config = dict((config or {}).get("repair_candidates", {}))
    if repair_config.get("enabled", True) is False or candidates.empty:
        return pd.DataFrame()
    max_repairs = int(repair_config.get("max_repair_candidates", 4))
    if max_repairs <= 0:
        return pd.DataFrame()
    step_fraction = float(repair_config.get("step_fraction", 0.10))
    # Ensure unique column names before concat (axis=1 joins in loop.py may create duplicates)
    history_clean = history.loc[:, ~history.columns.duplicated()].reset_index(drop=True)
    candidates_clean = candidates.loc[:, ~candidates.columns.duplicated()].reset_index(drop=True)
    bounds = pd.concat([history_clean, candidates_clean], ignore_index=True, sort=False)
    rows: list[dict[str, Any]] = []
    for _, candidate in candidates.iterrows():
        for feature_name in _violated_repair_features(candidate, config):
            for parameter, direction in REPAIR_ACTIONS.get(feature_name, []):
                repaired = _apply_bounded_repair(candidate, bounds, parameter, direction, step_fraction)
                if repaired is None:
                    continue
                repair_index = len(rows) + 1
                repaired["candidate_id"] = f"repair_{candidate.get('candidate_id', 'candidate')}_{feature_name}_{parameter}_{repair_index}"
                repaired["source"] = "constraint_ledger_repair"
                repaired["repair_trigger_feature"] = feature_name
                repaired["repair_parameter"] = parameter
                repaired["repair_action"] = direction
                repaired["changed_parameters"] = parameter
                repaired["must_resimulate"] = True
                repaired["data_source"] = "real_simulation_csv"
                repaired["engineering_validity"] = "simulation_only"
                rows.append(repaired)
                if len(rows) >= max_repairs:
                    return pd.DataFrame(rows)
    return pd.DataFrame(rows)


def _violated_repair_features(row: pd.Series, config: Mapping[str, Any] | None = None) -> list[str]:
    capm_config = dict(CAPM_DEFAULT_CONFIG)
    nested = (config or {}).get("capm_distance", {})
    if isinstance(nested, Mapping):
        capm_config.update(nested)
    violations: list[str] = []
    threshold_checks = [
        ("vgh_vth_margin", "low", capm_config["min_vgh_vth_margin"]),
        ("vgl_off_margin", "low", capm_config["min_vgl_off_margin"]),
        ("cboot_cload_ratio", "low", capm_config["min_cboot_cload_ratio"]),
        ("ron_pullup_cload_proxy", "high", capm_config["max_ron_pullup_cload_proxy"]),
        ("ron_pulldown_cload_proxy", "high", capm_config["max_ron_pulldown_cload_proxy"]),
        ("clk_slew_proxy", "high", capm_config["max_clk_slew_proxy"]),
    ]
    for feature_name, direction, threshold in threshold_checks:
        value = _numeric(row.get(feature_name))
        if value is None:
            continue
        if direction == "low" and value < float(threshold):
            violations.append(feature_name)
        if direction == "high" and value > float(threshold):
            violations.append(feature_name)
    return violations


def _apply_bounded_repair(
    row: pd.Series,
    bounds: pd.DataFrame,
    parameter: str,
    direction: str,
    step_fraction: float,
) -> dict[str, Any] | None:
    if parameter not in row or parameter not in bounds.columns:
        return None
    values = pd.to_numeric(bounds[parameter], errors="coerce").dropna()
    if values.empty:
        return None
    lower = float(values.min())
    upper = float(values.max())
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        return None
    current = _numeric(row.get(parameter))
    if current is None:
        return None
    step = max((upper - lower) * max(step_fraction, 0.0), 0.0)
    if step <= 0:
        return None
    if direction == "increase":
        new_value = min(current + step, upper)
    elif direction == "decrease":
        new_value = max(current - step, lower)
    else:
        return None
    if new_value == current:
        return None
    repaired = row.to_dict()
    repaired[parameter] = float(new_value)
    return repaired


def _numeric(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric
