import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import type { EvaluatedComparison } from "../types/product";

const client = createProductClient();
const labels: Record<string, string> = { improved: "Confirmed improvement", regressed: "Regression detected", neutral: "No material change", evidence_insufficient: "Evidence insufficient" };

export function ComparisonPage() {
  const { comparisonId = "" } = useParams();
  const [comparison, setComparison] = useState<EvaluatedComparison | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { client.getComparison(comparisonId).then(setComparison).catch((reason) => setError(String(reason))); }, [comparisonId]);
  return <>
    <header className="page-header"><div><p className="eyebrow">Comparison / evaluated evidence</p><h1>Evaluated comparison</h1><p className="page-description">Only imported simulation evidence can support a final improvement claim.</p></div></header>
    {error ? <div className="error-state"><p>{error}</p></div> : null}
    {comparison ? <>
      <div className={`verdict verdict--${comparison.verdict}`}><span>Verdict</span><strong>{labels[comparison.verdict] ?? comparison.verdict}</strong><p>{comparison.verdict === "evidence_insufficient" ? "The evidence chain is incomplete. Keep the candidate unconfirmed." : "The verdict was computed from evaluated baseline and result runs."}</p></div>
      <p className="record-line"><span>Baseline</span><code>{comparison.baseline_design_version_id}</code><span>Result</span><code>{comparison.result_design_version_id}</code></p>
      <div className="comparison-columns"><section className="section-panel"><div className="section-heading"><h2>Metric deltas</h2></div><pre className="json-summary">{JSON.stringify(comparison.metric_deltas, null, 2)}</pre></section><section className="section-panel"><div className="section-heading"><h2>Constraint changes</h2></div><pre className="json-summary">{JSON.stringify(comparison.constraint_changes, null, 2)}</pre></section></div>
    </> : null}
  </>;
}
