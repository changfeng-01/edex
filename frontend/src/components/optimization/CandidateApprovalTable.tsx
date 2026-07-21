import type { OptimizationCandidate } from "../../types/product";

interface Props {
  candidates: OptimizationCandidate[];
  busyId?: string | null;
  onApprove: (candidate: OptimizationCandidate) => void;
  onReject: (candidate: OptimizationCandidate) => void;
}

export function CandidateApprovalTable({ candidates, busyId, onApprove, onReject }: Props) {
  return <div className="data-table-wrap"><table className="data-table">
    <thead><tr><th>Candidate</th><th>Strategy</th><th>Proposed changes</th><th>Score</th><th>Transfer trust</th><th>Resimulation</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
    <tbody>{candidates.map((candidate) => <tr key={candidate.candidate_id}>
      <td><code>{candidate.candidate_id}</code></td>
      <td>{candidate.strategy}</td>
      <td><code>{JSON.stringify(candidate.parameter_changes)}</code></td>
      <td>{candidate.selection_score ?? "—"}</td>
      <td>{transferSummary(candidate)}</td>
      <td><code>must_resimulate = {String(candidate.must_resimulate)}</code></td>
      <td><span className={`workflow-badge workflow-badge--${candidate.status}`}>{candidate.status}</span></td>
      <td className="table-actions">
        {candidate.status === "proposed" ? <>
          <button className="button button--primary" disabled={busyId === candidate.candidate_id} onClick={() => onApprove(candidate)}>Approve candidate</button>
          <button className="button" disabled={busyId === candidate.candidate_id} onClick={() => onReject(candidate)}>Reject</button>
        </> : null}
      </td>
    </tr>)}</tbody>
  </table></div>;
}

function transferSummary(candidate: OptimizationCandidate) {
  const scores = candidate.selection_scores ?? {};
  const trust = scores.capm_transfer_trust_score;
  const status = scores.capm_transfer_status;
  if (typeof trust !== "number" && typeof status !== "string") return "—";
  const formattedTrust = typeof trust === "number" ? trust.toFixed(2) : "—";
  return <span title={typeof status === "string" ? status : undefined}>{formattedTrust}</span>;
}
