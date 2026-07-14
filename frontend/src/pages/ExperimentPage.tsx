import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import { CandidateApprovalTable } from "../components/optimization/CandidateApprovalTable";
import { ExperimentTimeline } from "../components/optimization/ExperimentTimeline";
import type { OptimizationCandidate, OptimizationExperiment } from "../types/product";

const client = createProductClient();

export function ExperimentPage() {
  const { experimentId = "" } = useParams();
  const navigate = useNavigate();
  const [experiment, setExperiment] = useState<OptimizationExperiment | null>(null);
  const [candidates, setCandidates] = useState<OptimizationCandidate[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([client.getExperiment(experimentId), client.listCandidates(experimentId)]).then(([nextExperiment, nextCandidates]) => { setExperiment(nextExperiment); setCandidates(nextCandidates); }).catch((reason) => setError(String(reason))); }, [experimentId]);
  const replaceCandidate = (next: OptimizationCandidate) => setCandidates((current) => current.map((item) => item.candidate_id === next.candidate_id ? next : item));
  const decide = async (candidate: OptimizationCandidate, decision: "approve" | "reject") => {
    setBusyId(candidate.candidate_id); setError("");
    try { replaceCandidate(decision === "approve" ? await client.approveCandidate(candidate.candidate_id) : await client.rejectCandidate(candidate.candidate_id, "operator_rejected")); }
    catch (reason) { setError(String(reason)); }
    finally { setBusyId(null); }
  };
  const createJob = async () => {
    const approvedIds = candidates.filter((candidate) => candidate.status === "approved").map((candidate) => candidate.candidate_id);
    if (!approvedIds.length) return;
    setBusyId("create-job"); setError("");
    try { const job = await client.createSimulationJob(approvedIds); navigate(`/simulation-jobs/${job.simulation_job_id}`); }
    catch (reason) { setError(String(reason)); }
    finally { setBusyId(null); }
  };
  return <>
    <header className="page-header"><div><p className="eyebrow">Experiment / {experiment?.state ?? "loading"}</p><h1>Optimization experiment</h1><p className="page-description">Review machine-generated proposals before creating a manual simulation batch.</p></div></header>
    <div className="evidence-strip"><strong className="evidence-strip__title">Engineering boundary</strong><code>data_source = real_simulation_csv</code><code>engineering_validity = simulation_only</code><span>Every proposal requires resimulation.</span></div>
    <ExperimentTimeline current={candidates[0]?.status ?? "proposed"} />
    {experiment ? <p className="record-line"><span>Baseline</span><code>{experiment.baseline_design_version_id}</code><span>Strategy</span><code>{JSON.stringify(experiment.strategy_config)}</code></p> : null}
    {error ? <div className="error-state"><p>{error}</p></div> : null}
    <section className="section-panel"><div className="section-heading section-heading--action"><div><h2>Candidate approval queue</h2><p>Approval authorizes export only. It does not execute a simulator.</p></div>{candidates.some((candidate) => candidate.status === "approved") ? <button className="button button--primary" disabled={busyId === "create-job"} onClick={() => void createJob()}>Create manual simulation job</button> : null}</div><CandidateApprovalTable candidates={candidates} busyId={busyId} onApprove={(candidate) => void decide(candidate, "approve")} onReject={(candidate) => void decide(candidate, "reject")} /></section>
  </>;
}
