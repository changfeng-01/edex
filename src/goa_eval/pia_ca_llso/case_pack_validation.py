"""Strict validation and publication reports for PIA evidence case packs."""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from goa_eval.io_utils import sha256_file, write_json
from goa_eval.pia_ca_llso.case_pack import BOUNDARY, CasePack, case_pack_to_protocol, load_case_pack, load_case_pack_root
from goa_eval.pia_ca_llso.value_coercion import finite_float, strict_bool


LEAKAGE_COLUMNS = {
    "overall_score",
    "hard_constraint_passed",
    "real_score",
    "target_hit",
    "simulation_result",
    "simulation_evidence_score",
    "simulation_evidence_hard_pass",
    "waveform_metric",
    "waveform_quality",
    "feasible_score",
}
LEAKAGE_TOKENS = ("waveform", "measured", "post_sim", "simulated_score")
PUBLICATION_FILES = [
    "case_pack_validation.json",
    "case_pack_validation.md",
    "publication_evidence_inventory.csv",
    "publication_summary.csv",
    "publication_win_rates.csv",
    "publication_claim_boundary_checklist.md",
    "publication_report.md",
    "source_lock.json",
]


def validate_case_pack(case_pack_dir: str | Path, strict_evidence: bool = False) -> dict[str, Any]:
    pack = load_case_pack(case_pack_dir)
    return validate_loaded_case_pack(pack, strict_evidence=strict_evidence)


def validate_loaded_case_pack(pack: CasePack, strict_evidence: bool = False) -> dict[str, Any]:
    _validate_boundary(pack)
    _require_candidate_id("history.csv", pack.history)
    _require_candidate_id("candidate_pool.csv", pack.candidates)
    leakage = _candidate_leakage_columns(pack.candidates)
    if leakage:
        raise ValueError(f"candidate_pool.csv contains result leakage columns: {', '.join(leakage)}")
    evidence_available = pack.results is not None and not pack.results.empty
    if pack.results is not None:
        _require_candidate_id("simulation_results.csv", pack.results)
        _validate_result_alignment(pack)
        _validate_result_values(pack, strict_evidence=strict_evidence)
        evidence_available = _has_usable_evidence(pack.results)
    if strict_evidence and not evidence_available:
        raise ValueError(f"case pack {pack.scenario_id} requires simulation_results.csv evidence in strict mode")
    return {
        "scenario_id": pack.scenario_id,
        "history_csv": str(pack.history_path),
        "candidate_csv": str(pack.candidate_path),
        "result_csv": str(pack.result_path),
        "methods": pack.methods,
        "seeds": pack.seeds,
        "top_k": pack.top_k,
        "target_score": pack.target_score,
        "history_rows": int(len(pack.history)),
        "candidate_rows": int(len(pack.candidates)),
        "result_rows": int(len(pack.results)) if pack.results is not None else 0,
        "evidence_available": bool(evidence_available),
        "selection_only": not bool(evidence_available),
        "included_in_statistical_claim": bool(evidence_available),
        **BOUNDARY,
    }


def run_case_pack_validation(
    case_pack: str | Path | None,
    case_pack_root: str | Path | None,
    output_dir: str | Path,
    *,
    strict_evidence: bool = False,
    command_args: Sequence[str] | None = None,
) -> dict[str, Any]:
    packs = [load_case_pack(case_pack)] if case_pack else load_case_pack_root(Path(case_pack_root or ""))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    validation_rows = [validate_loaded_case_pack(pack, strict_evidence=strict_evidence) for pack in packs]
    protocol = case_pack_to_protocol(packs)
    summary = _publication_summary(packs, validation_rows)
    win_rates = _publication_win_rates(summary)
    inventory = _evidence_inventory(packs, validation_rows)

    pd.DataFrame(inventory).to_csv(out / "publication_evidence_inventory.csv", index=False)
    summary.to_csv(out / "publication_summary.csv", index=False)
    win_rates.to_csv(out / "publication_win_rates.csv", index=False)
    write_json(
        out / "case_pack_validation.json",
        {
            "case_pack_count": len(packs),
            "strict_evidence": strict_evidence,
            "protocol": protocol,
            "validations": validation_rows,
            **BOUNDARY,
        },
    )
    (out / "case_pack_validation.md").write_text(_render_validation_markdown(validation_rows), encoding="utf-8")
    (out / "publication_claim_boundary_checklist.md").write_text(
        _render_claim_boundary_checklist(validation_rows),
        encoding="utf-8",
    )
    (out / "publication_report.md").write_text(
        _render_publication_report(summary, win_rates, validation_rows),
        encoding="utf-8",
    )
    write_json(
        out / "source_lock.json",
        _source_lock(packs, command_args=command_args or [], strict_evidence=strict_evidence),
    )
    return {
        "case_pack_count": len(packs),
        "strict_evidence": strict_evidence,
        "outputs": PUBLICATION_FILES,
        **BOUNDARY,
    }


def _publication_summary(packs: list[CasePack], validation_rows: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    validation_by_id = {row["scenario_id"]: row for row in validation_rows}
    for pack in packs:
        validation = validation_by_id[pack.scenario_id]
        if pack.results is None or pack.results.empty or not validation["included_in_statistical_claim"]:
            for method in pack.methods:
                rows.append(_selection_only_summary(pack, method))
            continue
        results = pack.results.copy()
        if "method" not in results.columns:
            results["method"] = pack.methods[0] if pack.methods else "imported_simulation"
        if "seed" not in results.columns:
            results["seed"] = pack.seeds[0] if pack.seeds else 0
        for (method, seed), group in results.groupby(["method", "seed"], dropna=False):
            rows.append(_method_summary(pack, str(method), int(seed), group))
    return pd.DataFrame(rows)


def _selection_only_summary(pack: CasePack, method: str) -> dict[str, Any]:
    return {
        "scenario_id": pack.scenario_id,
        "method": method,
        "seed": "",
        "budget": pack.top_k,
        "target_hit_rate": np.nan,
        "simulations_to_target": np.nan,
        "convergence_auc": np.nan,
        "best_evidence_score": np.nan,
        "evidence_available": False,
        "included_in_statistical_claim": False,
        **BOUNDARY,
    }


def _method_summary(pack: CasePack, method: str, seed: int, group: pd.DataFrame) -> dict[str, Any]:
    group = group.copy()
    if "budget_index" in group.columns:
        group["budget_index"] = pd.to_numeric(group["budget_index"], errors="coerce")
        group = group.sort_values("budget_index", kind="mergesort")
    scores = pd.to_numeric(group.get("overall_score", pd.Series(dtype=float)), errors="coerce")
    hard = group.get("hard_constraint_passed", pd.Series(True, index=group.index)).map(
        lambda value: strict_bool(value, field="hard_constraint_passed")
    )
    feasible_scores = scores.where(hard, other=np.nan)
    hits = (scores >= pack.target_score) & hard
    if "budget_index" in group.columns:
        budget_indices = pd.to_numeric(group["budget_index"], errors="coerce")
    else:
        budget_indices = pd.Series(range(1, len(group) + 1), index=group.index, dtype=float)
    hit_budgets = budget_indices[hits]
    curve = feasible_scores.cummax().dropna()
    return {
        "scenario_id": pack.scenario_id,
        "method": method,
        "seed": int(seed),
        "budget": pack.top_k,
        "target_hit_rate": float(hits.any()) if len(group) else 0.0,
        "simulations_to_target": float(hit_budgets.iloc[0]) if not hit_budgets.empty else np.nan,
        "convergence_auc": float(curve.mean()) if not curve.empty else np.nan,
        "best_evidence_score": float(feasible_scores.max()) if feasible_scores.notna().any() else np.nan,
        "evidence_available": True,
        "included_in_statistical_claim": True,
        **BOUNDARY,
    }


def _publication_win_rates(summary: pd.DataFrame) -> pd.DataFrame:
    evidence = summary[summary.get("included_in_statistical_claim", False).astype(bool)].copy()
    methods = sorted(summary["method"].dropna().astype(str).unique()) if "method" in summary else []
    wins = {method: 0 for method in methods}
    totals = {method: 0 for method in methods}
    if evidence.empty:
        return pd.DataFrame(
            [
                {
                    "method": method,
                    "scenario_wins": 0,
                    "scenario_comparisons": 0,
                    "win_rate": 0.0,
                    **BOUNDARY,
                }
                for method in methods
            ]
        )
    for _, group in evidence.groupby(["scenario_id", "seed"], dropna=False):
        ranked = group.sort_values(["target_hit_rate", "convergence_auc"], ascending=[False, False])
        if ranked.empty:
            continue
        present_methods = set(group["method"].dropna().astype(str))
        for method in present_methods:
            totals[method] += 1
        top = ranked.iloc[0]
        ties = ranked[
            (ranked["target_hit_rate"] == top["target_hit_rate"])
            & (ranked["convergence_auc"] == top["convergence_auc"])
        ]
        if len(ties) == 1:
            wins[str(top["method"])] += 1
    return pd.DataFrame(
        [
            {
                "method": method,
                "scenario_wins": int(wins[method]),
                "scenario_comparisons": int(totals[method]),
                "win_rate": float(wins[method] / totals[method]) if totals[method] else 0.0,
                **BOUNDARY,
            }
            for method in methods
        ]
    )


def _evidence_inventory(packs: list[CasePack], validation_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["scenario_id"]: row for row in validation_rows}
    rows = []
    for pack in packs:
        validation = by_id[pack.scenario_id]
        rows.append(
            {
                "scenario_id": pack.scenario_id,
                "history_csv": str(pack.history_path),
                "candidate_csv": str(pack.candidate_path),
                "result_csv": str(pack.result_path),
                "history_sha256": sha256_file(pack.history_path),
                "candidate_sha256": sha256_file(pack.candidate_path),
                "result_sha256": sha256_file(pack.result_path) if pack.result_path.exists() else "",
                "evidence_available": validation["evidence_available"],
                "included_in_statistical_claim": validation["included_in_statistical_claim"],
                **BOUNDARY,
            }
        )
    return rows


def _source_lock(packs: list[CasePack], command_args: Sequence[str], strict_evidence: bool) -> dict[str, Any]:
    input_paths = []
    for pack in packs:
        input_paths.extend([pack.root / "scenario.yaml", pack.history_path, pack.candidate_path, pack.scoring_config_path, pack.provenance_path])
        if pack.result_path.exists():
            input_paths.append(pack.result_path)
    unique_paths = sorted({path.resolve() for path in input_paths})
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command_args": list(command_args),
        "python_version": sys.version,
        "git_commit": _git_commit(),
        "strict_evidence": strict_evidence,
        "input_files": {
            str(path): {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in unique_paths
            if path.exists()
        },
        **BOUNDARY,
    }


def _render_validation_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# PIA Case Pack Validation",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "",
        "| Scenario | Evidence Available | Included In Claim | Selection Only |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario_id']} | {row['evidence_available']} | "
            f"{row['included_in_statistical_claim']} | {row['selection_only']} |"
        )
    return "\n".join(lines) + "\n"


def _render_claim_boundary_checklist(rows: list[dict[str, Any]]) -> str:
    selection_only = [row["scenario_id"] for row in rows if row["selection_only"]]
    lines = [
        "# Publication Claim Boundary Checklist",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- local/smoke fixtures are not physical validation",
        "- missing-evidence scenarios are selection-only and excluded from win rate / AUC conclusions",
        "",
        f"Selection-only scenarios: {', '.join(selection_only) if selection_only else 'none'}",
        "",
    ]
    return "\n".join(lines)


def _render_publication_report(summary: pd.DataFrame, win_rates: pd.DataFrame, rows: list[dict[str, Any]]) -> str:
    evidence_count = sum(1 for row in rows if row["evidence_available"])
    lines = [
        "# PIA-CA-LLSO Publication Evidence Report",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "",
        f"Evidence-backed scenarios: {evidence_count}/{len(rows)}",
        "",
        "## Publication Summary",
        _markdown_table(summary),
        "",
        "## Publication Win Rates",
        _markdown_table(win_rates),
        "",
        "Conclusion rule: only scenarios with imported simulation_results.csv evidence contribute to formal win rate, "
        "convergence AUC, and target-hit claims. Selection-only scenarios are retained for rerun planning.",
        "",
    ]
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows available._"
    text = frame.fillna("").astype(str)
    columns = list(text.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in text.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def _validate_boundary(pack: CasePack) -> None:
    boundary = pack.scenario.get("evidence_boundary", {})
    for field, expected in BOUNDARY.items():
        if boundary.get(field) != expected:
            raise ValueError(f"evidence_boundary.{field} must be {expected}")


def _require_candidate_id(name: str, frame: pd.DataFrame) -> None:
    if "candidate_id" not in frame.columns:
        raise ValueError(f"{name} must contain candidate_id")
    if frame["candidate_id"].isna().any():
        raise ValueError(f"{name} contains missing candidate_id values")


def _candidate_leakage_columns(candidates: pd.DataFrame) -> list[str]:
    blocked = []
    for column in candidates.columns:
        lowered = str(column).lower()
        if column in LEAKAGE_COLUMNS or any(token in lowered for token in LEAKAGE_TOKENS):
            blocked.append(str(column))
    return sorted(blocked)


def _validate_result_alignment(pack: CasePack) -> None:
    if pack.results is None or pack.results.empty:
        return
    candidate_ids = set(pack.candidates["candidate_id"].astype(str))
    result_ids = set(pack.results["candidate_id"].astype(str))
    missing = sorted(result_ids - candidate_ids)
    if missing:
        raise ValueError(f"simulation_results.csv contains candidate_id values missing from candidate_pool.csv: {', '.join(missing)}")


def _validate_result_values(pack: CasePack, *, strict_evidence: bool) -> None:
    if pack.results is None or pack.results.empty:
        return
    results = pack.results
    required = {"candidate_id", "overall_score", "hard_constraint_passed"}
    missing = sorted(required - set(results.columns))
    if missing:
        raise ValueError(f"simulation_results.csv missing required columns: {', '.join(missing)}")
    candidate_ids = results["candidate_id"].astype("string")
    if (candidate_ids.isna() | candidate_ids.str.strip().eq("")).any():
        raise ValueError("simulation_results.csv candidate_id must not be empty")
    results["candidate_id"] = candidate_ids.str.strip().astype(str)
    results["overall_score"] = [finite_float(value, field="overall_score") for value in results["overall_score"]]
    results["hard_constraint_passed"] = [
        strict_bool(value, field="hard_constraint_passed") for value in results["hard_constraint_passed"]
    ]
    if not strict_evidence:
        return
    strict_columns = {"method", "seed", "budget_index"}
    missing_strict = sorted(strict_columns - set(results.columns))
    if missing_strict:
        raise ValueError(f"strict evidence results missing columns: {', '.join(missing_strict)}")
    results["budget_index"] = pd.to_numeric(results["budget_index"], errors="coerce")
    if results["budget_index"].isna().any():
        raise ValueError("budget_index must be numeric in strict evidence mode")
    duplicate_budget = results.duplicated(["method", "seed", "budget_index"], keep=False)
    if duplicate_budget.any():
        raise ValueError("duplicate budget_index for method and seed in strict evidence mode")
    invalid_budget = (results["budget_index"] < 1) | (results["budget_index"] > pack.top_k)
    if invalid_budget.any():
        raise ValueError(f"budget_index must be between 1 and top_k={pack.top_k}")
    present = set(zip(results["method"].astype(str), pd.to_numeric(results["seed"], errors="coerce")))
    expected = {(method, seed) for method in pack.methods for seed in pack.seeds}
    missing_pairs = sorted(expected - present)
    if missing_pairs:
        raise ValueError(f"strict evidence missing method/seed results: {missing_pairs}")


def _has_usable_evidence(results: pd.DataFrame) -> bool:
    required = {"candidate_id", "overall_score", "hard_constraint_passed"}
    if not required.issubset(results.columns):
        return False
    return pd.to_numeric(results["overall_score"], errors="coerce").notna().any()


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"
