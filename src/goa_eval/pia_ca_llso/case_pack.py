"""Evidence case-pack schema helpers for PIA-CA-LLSO publication audits."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from goa_eval.pia_ca_llso import DATA_SOURCE, ENGINEERING_VALIDITY
from goa_eval.pia_ca_llso.io import read_config, write_json


BOUNDARY = {
    "data_source": DATA_SOURCE,
    "engineering_validity": ENGINEERING_VALIDITY,
    "must_resimulate": True,
}
REQUIRED_FILES = [
    "scenario.yaml",
    "history.csv",
    "candidate_pool.csv",
    "simulation_results.csv",
    "scoring_config.yaml",
    "provenance.json",
]


@dataclass(frozen=True)
class CasePack:
    root: Path
    scenario: dict[str, Any]
    history_path: Path
    candidate_path: Path
    result_path: Path
    scoring_config_path: Path
    provenance_path: Path
    history: pd.DataFrame
    candidates: pd.DataFrame
    results: pd.DataFrame | None
    scoring_config: dict[str, Any]
    provenance: dict[str, Any]

    @property
    def scenario_id(self) -> str:
        return str(self.scenario["scenario_id"])

    @property
    def methods(self) -> list[str]:
        return [str(item) for item in self.scenario.get("methods", [])]

    @property
    def seeds(self) -> list[int]:
        return [int(item) for item in self.scenario.get("seeds", [])]

    @property
    def top_k(self) -> int:
        return int(self.scenario.get("top_k", 0))

    @property
    def target_score(self) -> float:
        return float(self.scenario.get("target_score", self.scoring_config.get("target_score", 80.0)))


def export_case_pack_template(output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scenario = {
        "scenario_id": "TODO_SCENARIO_ID",
        "history_csv": "history.csv",
        "candidate_csv": "candidate_pool.csv",
        "result_csv": "simulation_results.csv",
        "methods": ["pia_full", "pia_no_repair", "paper_baseline"],
        "seeds": [1],
        "top_k": 4,
        "target_score": 80,
        "evidence_boundary": dict(BOUNDARY),
    }
    (out / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    pd.DataFrame(columns=["sample_id", "candidate_id", "overall_score", "hard_constraint_passed"]).to_csv(
        out / "history.csv",
        index=False,
    )
    pd.DataFrame(columns=["candidate_id", "parameter_1", "parameter_2"]).to_csv(out / "candidate_pool.csv", index=False)
    pd.DataFrame(
        columns=["candidate_id", "method", "seed", "budget_index", "overall_score", "hard_constraint_passed"]
    ).to_csv(out / "simulation_results.csv", index=False)
    (out / "scoring_config.yaml").write_text("target_score: 80\n", encoding="utf-8")
    write_json(out / "provenance.json", {"source": "TODO", "notes": []})
    return out


def load_case_pack(case_pack_dir: str | Path) -> CasePack:
    root = Path(case_pack_dir)
    scenario_path = root / "scenario.yaml"
    if not scenario_path.exists():
        raise FileNotFoundError(str(scenario_path))
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    _require_scenario_fields(scenario)
    history_path = _resolve(root, scenario["history_csv"])
    candidate_path = _resolve(root, scenario["candidate_csv"])
    result_path = _resolve(root, scenario.get("result_csv", "simulation_results.csv"))
    scoring_config_path = _resolve(root, scenario.get("scoring_config", "scoring_config.yaml"))
    provenance_path = _resolve(root, scenario.get("provenance", "provenance.json"))
    for path in [history_path, candidate_path, scoring_config_path, provenance_path]:
        if not path.exists():
            raise FileNotFoundError(str(path))
    return CasePack(
        root=root,
        scenario=dict(scenario),
        history_path=history_path,
        candidate_path=candidate_path,
        result_path=result_path,
        scoring_config_path=scoring_config_path,
        provenance_path=provenance_path,
        history=pd.read_csv(history_path),
        candidates=pd.read_csv(candidate_path),
        results=pd.read_csv(result_path) if result_path.exists() else None,
        scoring_config=read_config(scoring_config_path),
        provenance=read_config(provenance_path),
    )


def load_case_pack_root(case_pack_root: str | Path) -> list[CasePack]:
    root = Path(case_pack_root)
    if not root.exists():
        raise FileNotFoundError(str(root))
    if (root / "scenario.yaml").exists():
        return [load_case_pack(root)]
    packs = [load_case_pack(path) for path in sorted(root.iterdir()) if path.is_dir() and (path / "scenario.yaml").exists()]
    if not packs:
        raise ValueError(f"no case packs found under {root}")
    return packs


def case_pack_to_protocol(case_packs: Iterable[CasePack]) -> dict[str, Any]:
    packs = list(case_packs)
    if not packs:
        raise ValueError("case_pack_to_protocol requires at least one case pack")
    methods = _ordered_unique(method for pack in packs for method in pack.methods)
    seeds = _ordered_unique(seed for pack in packs for seed in pack.seeds)
    first = packs[0]
    return {
        "name": "pia_ca_llso_phase4_case_pack_validation",
        "target_score": first.target_score,
        "top_k": first.top_k,
        "methods": methods,
        "seeds": seeds,
        "boundary": dict(BOUNDARY),
        "scenarios": [
            {
                "scenario_id": pack.scenario_id,
                "history_csv": str(pack.history_path),
                "candidate_csv": str(pack.candidate_path),
                "result_csv": str(pack.result_path),
                "scoring_config": str(pack.scoring_config_path),
                "provenance": str(pack.provenance_path),
                "evidence_available": pack.results is not None and not pack.results.empty,
            }
            for pack in packs
        ],
    }


def _require_scenario_fields(scenario: dict[str, Any]) -> None:
    required = [
        "scenario_id",
        "history_csv",
        "candidate_csv",
        "result_csv",
        "methods",
        "seeds",
        "top_k",
        "target_score",
        "evidence_boundary",
    ]
    missing = [field for field in required if field not in scenario]
    if missing:
        raise ValueError(f"case pack scenario missing required fields: {', '.join(missing)}")


def _resolve(root: Path, raw: Any) -> Path:
    path = Path(str(raw))
    return path if path.is_absolute() else root / path


def _ordered_unique(values: Iterable[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output
