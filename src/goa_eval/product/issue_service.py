from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

from goa_eval.product.models import IssueRecord


KNOWN_ISSUES = {
    "Max_ripple": {
        "key": "FAIL_RIPPLE",
        "category": "waveform_quality",
        "metric": "max_ripple",
        "causes": ("output-node settling or charge retention may be insufficient",),
        "actions": ("inspect ripple by stage and resimulate after bounded parameter changes",),
    },
    "Max_overlap_ratio": {
        "key": "FAIL_OVERLAP",
        "category": "timing",
        "metric": "max_overlap_ratio",
        "causes": ("adjacent-stage timing or edge rate may create excess overlap",),
        "actions": ("inspect neighboring stage edges and resimulate timing changes",),
    },
    "Max_voltage_loss": {
        "key": "FAIL_VOLTAGE_LOSS",
        "category": "waveform_quality",
        "metric": "max_voltage_loss",
        "causes": ("hold-path leakage or drive strength may be insufficient",),
        "actions": ("inspect worst-stage voltage loss and resimulate drive changes",),
    },
    "Delay_std": {
        "key": "FAIL_DELAY",
        "category": "timing",
        "metric": "delay_std",
        "causes": ("stage-to-stage loading variation may increase delay spread",),
        "actions": ("inspect delay distribution and resimulate bounded timing changes",),
    },
    "VOH_min_margin": {
        "key": "FAIL_VOH",
        "category": "signal_integrity",
        "metric": "voh_min",
        "causes": ("drive or load conditions may reduce the high-level margin",),
        "actions": ("inspect the worst VOH stage and resimulate drive/load changes",),
    },
    "All_pulses_exist": {
        "key": "FAIL_PULSE_MISSING",
        "category": "functional",
        "metric": "all_pulses_exist",
        "causes": ("pulse propagation may fail at one or more stages",),
        "actions": ("inspect the first missing pulse and resimulate the propagation path",),
    },
    "Seq_pass": {
        "key": "FAIL_SEQUENCE",
        "category": "functional",
        "metric": "seq_pass",
        "causes": ("stage activation order may violate the expected sequence",),
        "actions": ("inspect stage ordering and resimulate timing controls",),
    },
    "FalseTriggerCount": {
        "key": "FAIL_FALSE_TRIGGER",
        "category": "functional",
        "metric": "false_trigger_count",
        "causes": ("noise or coupling may create unintended stage activation",),
        "actions": ("inspect false-trigger windows and resimulate isolation changes",),
    },
}


class IssueService:
    def build_issues(
        self,
        score: Mapping[str, Any],
        summary: Mapping[str, Any],
        metrics: Iterable[Mapping[str, Any]],
        diagnosis_ref: str | None,
    ) -> tuple[IssueRecord, ...]:
        failed = [
            (str(name), details)
            for name, details in (score.get("hard_constraints") or {}).items()
            if isinstance(details, Mapping) and details.get("passed") is False
        ]
        if not failed and str(summary.get("Overall_status", "PASS")).startswith("FAIL"):
            failed = [(str(summary["Overall_status"]), {})]
        metric_rows = list(metrics)
        return tuple(
            self._build_issue(name, details, summary, metric_rows, diagnosis_ref, len(failed))
            for name, details in failed
        )

    @staticmethod
    def _build_issue(
        name: str,
        details: Mapping[str, Any],
        summary: Mapping[str, Any],
        metrics: list[Mapping[str, Any]],
        diagnosis_ref: str | None,
        failure_count: int,
    ) -> IssueRecord:
        known = KNOWN_ISSUES.get(name)
        if known is None and name.startswith("FAIL_"):
            known = next((value for value in KNOWN_ISSUES.values() if value["key"] == name), None)
        status = str(summary.get("Overall_status") or "")
        constraint_key = str(known["key"]) if known else (status if failure_count == 1 and status.startswith("FAIL_") else f"FAIL_{name.upper()}")
        worst_stage = summary.get("worst_stage")
        affected = (f"o{int(worst_stage)}",) if isinstance(worst_stage, (int, float)) else ()
        if not affected and metrics:
            stage = metrics[0].get("stage") or metrics[0].get("stage_index")
            affected = (f"o{int(stage)}",) if isinstance(stage, (int, float)) else ()
        seed = f"{constraint_key}|{','.join(affected)}"
        return IssueRecord(
            issue_id=f"issue_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex}",
            constraint_key=constraint_key,
            category=str(known["category"]) if known else "unclassified",
            severity="high",
            affected_nodes=affected,
            metric_refs=(str(known["metric"]),) if known else (),
            possible_causes=tuple(known["causes"]) if known else (),
            recommended_actions=tuple(known["actions"]) if known else (),
            evidence_refs=(diagnosis_ref,) if diagnosis_ref else (),
            classification="known" if known else "unclassified",
        )
