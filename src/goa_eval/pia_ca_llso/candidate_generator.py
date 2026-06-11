from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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
