import { CheckCircle2, XCircle } from "lucide-react";

import { toFixedNumber, toPercent } from "../data/loaders";
import type { ScoreSummary } from "../types";

export function ConstraintPanel({ score }: { score: ScoreSummary }) {
  const entries = Object.entries(score.hard_constraints);
  return (
    <section className="section-block" aria-label="硬约束">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Hard constraints</span>
          <h2>硬约束检查</h2>
        </div>
        <span className={score.hard_constraint_passed ? "label-pass" : "label-fail"}>
          {score.hard_constraint_passed ? "PASSED" : "NEEDS REVIEW"}
        </span>
      </div>
      <div className="constraint-list">
        {entries.map(([name, item]) => (
          <div className="constraint-row" key={name}>
            <div className={item.passed ? "constraint-status ok" : "constraint-status fail"}>
              {item.passed ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
            </div>
            <div>
              <strong>{name}</strong>
              <span>{item.reason}</span>
            </div>
            <div className="constraint-values">
              <span>{formatConstraintValue(name, item.current_value)}</span>
              <small>limit {formatConstraintValue(name, item.threshold)}</small>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatConstraintValue(name: string, value: boolean | number | string | null): string {
  if (value === null) {
    return "N/A";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    if (name.toLowerCase().includes("ratio")) {
      return toPercent(value);
    }
    return toFixedNumber(value, value < 1 ? 3 : 1);
  }
  return value;
}
