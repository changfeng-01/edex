import { AlertOctagon, HelpCircle } from "lucide-react";

import type { IssueRecord } from "../../types/product";

export function IssueList({ issues }: { issues: IssueRecord[] }) {
  if (!issues.length) return <p className="muted">No failed constraints were indexed.</p>;
  return (
    <div className="issue-list">
      {issues.map((issue) => (
        <article className="issue-row" key={issue.issue_id}>
          {issue.classification === "unclassified" ? <HelpCircle aria-hidden="true" /> : <AlertOctagon aria-hidden="true" />}
          <div><strong>{issue.constraint_key}</strong><p>{issue.category} · {issue.severity} · {issue.classification}</p></div>
          <code title={issue.issue_id}>{issue.issue_id}</code>
        </article>
      ))}
    </div>
  );
}
