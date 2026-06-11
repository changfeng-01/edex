from __future__ import annotations

import json
from typing import Any

import pandas as pd


def attach_constraint_ledger(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    constraints = config.get("constraints") or config.get("constraint_specs") or {}
    ledger_rows: list[str] = []
    violations: list[float] = []
    for _, row in output.iterrows():
        row_ledger = []
        total_violation = 0.0
        for name, rule in constraints.items():
            value = row.get(name)
            passed = True
            violation = 0.0
            if value is None or pd.isna(value):
                passed = False
                violation = 1.0
            elif "min" in rule and float(value) < float(rule["min"]):
                passed = False
                violation = (float(rule["min"]) - float(value)) / max(abs(float(rule["min"])), 1.0)
            elif "max" in rule and float(value) > float(rule["max"]):
                passed = False
                violation = (float(value) - float(rule["max"])) / max(abs(float(rule["max"])), 1.0)
            total_violation += max(0.0, violation)
            row_ledger.append({"name": name, "value": None if pd.isna(value) else value, "passed": passed, "violation": violation})
        ledger_rows.append(json.dumps(row_ledger, ensure_ascii=False))
        violations.append(total_violation)
    output["constraint_ledger_json"] = ledger_rows
    output["constraint_violation"] = violations
    if "hard_constraint_passed" not in output.columns and constraints:
        output["hard_constraint_passed"] = [violation == 0 for violation in violations]
    return output
