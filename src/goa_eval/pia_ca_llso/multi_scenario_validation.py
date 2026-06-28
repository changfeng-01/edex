from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from goa_eval.pia_ca_llso.paper_reproduction import _attach_imported_evidence, _method_metrics, _select_method


DEFAULT_MULTI_SCENARIO_METHODS = ["pia_full", "pia_no_repair", "paper_adaptive_constraint_eval"]
DEFAULT_MULTI_SCENARIO_SEEDS = list(range(1, 11))


@dataclass
class MaterializedScenario:
    scenario_id: str
    history: pd.DataFrame
    candidates: pd.DataFrame
    evidence: pd.DataFrame
    evidence_available: bool
    sparse_history: bool
    metadata: dict[str, Any]


def materialize_validation_scenario(scenario: Mapping[str, Any]) -> MaterializedScenario:
    scenario_id = str(scenario.get("scenario_id", "scenario"))
    history = pd.read_csv(str(scenario["history_csv"]))
    candidates = pd.read_csv(str(scenario["candidate_csv"]))
    history = _ensure_sample_id(history)
    candidate_format = str(scenario.get("candidate_format", "") or "")
    if candidate_format == "action_recommendations" or "parameters_json" in candidates.columns:
        candidates = _materialize_action_candidates(candidates)
    candidates = _ensure_candidate_id(candidates)
    candidates["must_resimulate"] = True
    candidates["data_source"] = "real_simulation_csv"
    candidates["engineering_validity"] = "simulation_only"
    sparse_history = len(history) < 4
    evidence = _candidate_evidence_from_scenario(history, candidates, scenario)
    evidence_available = not evidence.empty and evidence["overall_score"].notna().any()
    return MaterializedScenario(
        scenario_id=scenario_id,
        history=history,
        candidates=candidates,
        evidence=evidence,
        evidence_available=bool(evidence_available),
        sparse_history=bool(sparse_history),
        metadata={
            "candidate_format": candidate_format or "direct_csv",
            "evidence_available": bool(evidence_available),
            "sparse_history": bool(sparse_history),
            "history_rows": int(len(history)),
            "candidate_rows": int(len(candidates)),
        },
    )


def run_multi_scenario_validation(
    protocol: Mapping[str, Any],
    output_dir: str | Path,
    seeds: Sequence[int] | None = None,
    methods: Sequence[str] | None = None,
    top_k: int | None = None,
    target_score: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    active_seeds = list(seeds or protocol.get("seeds") or DEFAULT_MULTI_SCENARIO_SEEDS)
    active_methods = list(methods or protocol.get("methods") or DEFAULT_MULTI_SCENARIO_METHODS)
    budget = int(top_k if top_k is not None else protocol.get("top_k", 4))
    target = float(target_score if target_score is not None else protocol.get("target_score", 80.0))
    scenarios = [materialize_validation_scenario(item) for item in protocol.get("scenarios", [])]
    if not scenarios:
        raise ValueError("multi-scenario validation requires at least one scenario")

    run_rows: list[dict[str, Any]] = []
    method_summary_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for seed in active_seeds:
            seeded_candidates = _seed_candidates(scenario.candidates, int(seed))
            for method in active_methods:
                selected = _select_multiscenario_method(method, scenario.history, seeded_candidates, top_k=budget, config=config)
                selected = _attach_imported_evidence(selected, scenario.evidence)
                selected["scenario_id"] = scenario.scenario_id
                selected["seed"] = int(seed)
                selected["method"] = method
                selected["budget"] = budget
                selected["budget_index"] = range(1, len(selected) + 1)
                selected["evidence_available"] = scenario.evidence_available
                selected["included_in_statistical_claim"] = bool(scenario.evidence_available)
                selected["sparse_history"] = scenario.sparse_history
                selected["data_source"] = "real_simulation_csv"
                selected["engineering_validity"] = "simulation_only"
                selected["must_resimulate"] = True
                metrics = _method_metrics(selected, target_score=target)
                method_summary_rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "seed": int(seed),
                        "method": method,
                        "budget": budget,
                        "evidence_available": scenario.evidence_available,
                        "included_in_statistical_claim": bool(scenario.evidence_available),
                        "sparse_history": scenario.sparse_history,
                        **{key: value for key, value in metrics.items() if key != "convergence_curve"},
                    }
                )
                run_rows.extend(selected.to_dict("records"))

    runs = pd.DataFrame(run_rows)
    per_seed = pd.DataFrame(method_summary_rows)
    summary = _aggregate_summary(per_seed)
    win_rates = _multi_scenario_win_rates(per_seed)
    majority = _majority_vote(win_rates)
    no_repair = _no_repair_ablation(per_seed)

    runs.to_csv(out / "multi_scenario_runs.csv", index=False)
    per_seed.to_csv(out / "multi_scenario_seed_metrics.csv", index=False)
    summary.to_csv(out / "multi_scenario_summary.csv", index=False)
    win_rates.to_csv(out / "multi_scenario_win_rates.csv", index=False)
    majority.to_csv(out / "majority_vote_summary.csv", index=False)
    no_repair.to_csv(out / "no_repair_ablation_summary.csv", index=False)
    scenario_manifest = [scenario.metadata | {"scenario_id": scenario.scenario_id} for scenario in scenarios]
    (out / "multi_scenario_manifest.json").write_text(json.dumps(scenario_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "multi_scenario_validation_report.md").write_text(
        render_multi_scenario_report(summary, win_rates, majority, no_repair, scenario_manifest, active_methods, active_seeds, target),
        encoding="utf-8",
    )
    result = {
        "scenario_count": len(scenarios),
        "seed_count": len(active_seeds),
        "methods": active_methods,
        "target_score": target,
        "top_k": budget,
        "data_source": "real_simulation_csv",
        "engineering_validity": "simulation_only",
        "must_resimulate": True,
        "outputs": [
            "multi_scenario_runs.csv",
            "multi_scenario_summary.csv",
            "multi_scenario_win_rates.csv",
            "majority_vote_summary.csv",
            "no_repair_ablation_summary.csv",
            "multi_scenario_validation_report.md",
        ],
    }
    (out / "multi_scenario_validation_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def render_multi_scenario_report(
    summary: pd.DataFrame,
    win_rates: pd.DataFrame,
    majority: pd.DataFrame,
    no_repair: pd.DataFrame,
    scenario_manifest: list[dict[str, Any]],
    methods: Sequence[str],
    seeds: Sequence[int],
    target_score: float,
) -> str:
    lines = [
        "# PIA-CA-LLSO Multi-Scenario Validation",
        "",
        "- data_source = real_simulation_csv",
        "- engineering_validity = simulation_only",
        "- must_resimulate = true",
        "- evidence_missing scenarios are selection-only and excluded from statistical claims",
        "",
        f"Target score: {target_score}",
        f"Methods: {', '.join(methods)}",
        f"Seeds: {list(seeds)}",
        "",
        "## Scenario Evidence",
        "",
        "| Scenario | Evidence Available | Sparse History | Candidate Rows |",
        "|---|---:|---:|---:|",
    ]
    for item in scenario_manifest:
        lines.append(
            f"| {item.get('scenario_id')} | {item.get('evidence_available')} | "
            f"{item.get('sparse_history')} | {item.get('candidate_rows')} |"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Scenario | Method | Included | Hit Rate Mean | Hit Rate Std | AUC Mean | AUC Std |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['scenario_id']} | {row['method']} | {row['included_in_statistical_claim']} | "
            f"{float(row.get('target_hit_rate_mean', 0.0)):.3f} | {float(row.get('target_hit_rate_std', 0.0)):.3f} | "
            f"{float(row.get('convergence_auc_mean', 0.0)):.3f} | {float(row.get('convergence_auc_std', 0.0)):.3f} |"
        )
    lines.extend(["", "## Win Rates", "", "| Method | Win Rate | Scenario Wins |", "|---|---:|---:|"])
    for _, row in win_rates.iterrows():
        lines.append(f"| {row['method']} | {float(row.get('win_rate', 0.0)):.3f} | {int(row.get('scenario_wins', 0))} |")
    lines.extend(["", "## Majority Vote", "", _markdown_table(majority) if not majority.empty else "No evidence-backed scenarios."])
    lines.extend(["", "## No Repair Ablation", "", _markdown_table(no_repair) if not no_repair.empty else "No evidence-backed no-repair comparison."])
    lines.extend(
        [
            "",
            "Conclusion rule: only evidence-backed scenarios contribute to mean/std, win rate, and majority claims. "
            "Selection-only rows are retained for next-run simulation planning, not for superiority claims.",
            "",
        ]
    )
    return "\n".join(lines)


def _select_multiscenario_method(
    method: str,
    history: pd.DataFrame,
    candidates: pd.DataFrame,
    top_k: int,
    config: Mapping[str, Any] | None,
) -> pd.DataFrame:
    if method == "pia_full":
        return _select_method("classifier_level_hybrid", history, candidates, candidates, top_k=top_k, config=config)
    if method == "pia_no_repair":
        no_repair_config = copy.deepcopy(dict(config or {}))
        no_repair_config.setdefault("repair_candidates", {})["enabled"] = False
        selected = _select_method("classifier_level_hybrid", history, candidates, candidates, top_k=top_k, config=no_repair_config)
        return selected[selected.get("source", pd.Series("", index=selected.index)).fillna("") != "constraint_ledger_repair"].head(top_k)
    if method == "paper_adaptive_constraint_eval":
        return _select_method("paper_adaptive_constraint_eval", history, candidates, candidates, top_k=top_k, config=config)
    return _select_method(method, history, candidates, candidates, top_k=top_k, config=config)


def _aggregate_summary(per_seed: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = ["target_hit_rate", "convergence_auc", "best_evidence_score", "mean_acquisition_score"]
    group_cols = ["scenario_id", "method"]
    for (scenario_id, method), group in per_seed.groupby(group_cols, dropna=False):
        row: dict[str, Any] = {
            "scenario_id": scenario_id,
            "method": method,
            "seed_count": int(group["seed"].nunique()),
            "budget": int(group["budget"].iloc[0]) if not group.empty else 0,
            "evidence_available": bool(group["evidence_available"].all()),
            "included_in_statistical_claim": bool(group["included_in_statistical_claim"].all()),
            "sparse_history": bool(group["sparse_history"].all()),
            "data_source": "real_simulation_csv",
            "engineering_validity": "simulation_only",
            "must_resimulate": True,
        }
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce")
            if not bool(row["included_in_statistical_claim"]):
                row[f"{metric}_mean"] = np.nan
                row[f"{metric}_std"] = np.nan
            else:
                row[f"{metric}_mean"] = float(values.mean()) if values.notna().any() else np.nan
                row[f"{metric}_std"] = float(values.std(ddof=0)) if values.notna().any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _multi_scenario_win_rates(per_seed: pd.DataFrame) -> pd.DataFrame:
    evidence = per_seed[per_seed["included_in_statistical_claim"].astype(bool)].copy()
    methods = sorted(per_seed["method"].dropna().unique())
    wins = {method: 0 for method in methods}
    totals = {method: 0 for method in methods}
    for scenario_id, scenario_group in evidence.groupby("scenario_id"):
        scores = []
        for method, group in scenario_group.groupby("method"):
            scores.append(
                {
                    "method": method,
                    "target_hit_rate": float(pd.to_numeric(group["target_hit_rate"], errors="coerce").mean()),
                    "convergence_auc": float(pd.to_numeric(group["convergence_auc"], errors="coerce").mean()),
                }
            )
        if not scores:
            continue
        for method in methods:
            totals[method] += 1
        best_hit = max(row["target_hit_rate"] for row in scores)
        best_auc = max(row["convergence_auc"] for row in scores if row["target_hit_rate"] == best_hit)
        winners = [row["method"] for row in scores if row["target_hit_rate"] == best_hit and row["convergence_auc"] == best_auc]
        if len(winners) == 1:
            wins[winners[0]] += 1
    return pd.DataFrame(
        [
            {
                "method": method,
                "scenario_wins": int(wins[method]),
                "scenario_comparisons": int(totals[method]),
                "win_rate": float(wins[method] / totals[method]) if totals[method] else 0.0,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
            for method in methods
        ]
    )


def _majority_vote(win_rates: pd.DataFrame) -> pd.DataFrame:
    if win_rates.empty:
        return pd.DataFrame(columns=["method", "majority_scenario_win_rate", "majority_winner"])
    rows = []
    max_rate = float(win_rates["win_rate"].max())
    for _, row in win_rates.iterrows():
        rate = float(row["win_rate"])
        rows.append(
            {
                "method": row["method"],
                "majority_scenario_win_rate": rate,
                "majority_winner": bool(rate == max_rate and rate > 0.5),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        )
    return pd.DataFrame(rows)


def _no_repair_ablation(per_seed: pd.DataFrame) -> pd.DataFrame:
    evidence = per_seed[per_seed["included_in_statistical_claim"].astype(bool)]
    rows = []
    for scenario_id, group in evidence.groupby("scenario_id"):
        full = group[group["method"] == "pia_full"]
        no_repair = group[group["method"] == "pia_no_repair"]
        if full.empty or no_repair.empty:
            continue
        rows.append(
            {
                "comparison": "pia_full_vs_pia_no_repair",
                "scenario_id": scenario_id,
                "target_hit_rate_delta": float(full["target_hit_rate"].mean() - no_repair["target_hit_rate"].mean()),
                "convergence_auc_delta": float(full["convergence_auc"].mean() - no_repair["convergence_auc"].mean()),
                "repair_helped": bool(
                    (full["target_hit_rate"].mean() > no_repair["target_hit_rate"].mean())
                    or (full["convergence_auc"].mean() > no_repair["convergence_auc"].mean())
                ),
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        )
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(
        [
            {
                "comparison": "pia_full_vs_pia_no_repair",
                "scenario_id": "",
                "target_hit_rate_delta": np.nan,
                "convergence_auc_delta": np.nan,
                "repair_helped": False,
                "data_source": "real_simulation_csv",
                "engineering_validity": "simulation_only",
                "must_resimulate": True,
            }
        ]
    )


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(str(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(row[column]) else str(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def _materialize_action_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    output = candidates.copy()
    for index, row in output.iterrows():
        values = _parse_parameters_json(row.get("parameters_json"))
        parameter = row.get("parameter")
        if isinstance(parameter, str) and parameter and parameter not in values:
            try:
                values[parameter] = float(row.get("candidate_value"))
            except (TypeError, ValueError):
                pass
        for key, value in values.items():
            output.loc[index, key] = value
    return output


def _parse_parameters_json(value: Any) -> dict[str, float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    result = {}
    for key, raw in payload.items():
        try:
            result[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return result


def _ensure_sample_id(history: pd.DataFrame) -> pd.DataFrame:
    output = history.copy()
    if "sample_id" not in output.columns:
        if "run_id" in output.columns:
            output.insert(0, "sample_id", output["run_id"].astype(str))
        else:
            output.insert(0, "sample_id", [f"h{idx + 1}" for idx in range(len(output))])
    return output


def _ensure_candidate_id(candidates: pd.DataFrame) -> pd.DataFrame:
    output = candidates.copy()
    if "candidate_id" not in output.columns:
        output.insert(0, "candidate_id", [f"candidate_{idx + 1}" for idx in range(len(output))])
    return output


def _seed_candidates(candidates: pd.DataFrame, seed: int) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    return candidates.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def _candidate_evidence_from_scenario(history: pd.DataFrame, candidates: pd.DataFrame, scenario: Mapping[str, Any]) -> pd.DataFrame:
    source = str(scenario.get("candidate_evidence_source", "candidates"))
    if source == "history_by_candidate_id" and "candidate_id" in history.columns:
        evidence = history.copy()
    else:
        evidence = candidates.copy()
    required = ["candidate_id", "overall_score", "hard_constraint_passed"]
    if not set(required).issubset(evidence.columns):
        return pd.DataFrame(columns=required)
    columns = [column for column in ["candidate_id", "overall_score", "hard_constraint_passed", "sim_success", "status", "constraint_violation"] if column in evidence.columns]
    return evidence[columns].copy()


def _merge_evidence_into_candidates(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    drop_cols = [column for column in ["overall_score", "hard_constraint_passed", "sim_success", "status", "constraint_violation"] if column in candidates.columns]
    base = candidates.drop(columns=drop_cols, errors="ignore")
    return base.merge(evidence, on="candidate_id", how="left")
