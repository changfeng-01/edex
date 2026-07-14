import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import { ExperimentTimeline } from "../components/optimization/ExperimentTimeline";
import { SimulationImportPanel } from "../components/optimization/SimulationImportPanel";
import type { SimulationImportPreview, SimulationJob } from "../types/product";

const client = createProductClient();

export function SimulationJobPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<SimulationJob | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SimulationImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { client.getSimulationJob(jobId).then(setJob).catch((reason) => setError(String(reason))); }, [jobId]);
  const previewImport = async () => { if (!file) return; setBusy(true); setError(""); try { setPreview(await client.previewSimulationImport(jobId, file)); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } };
  const commitImport = async () => { if (!preview) return; setBusy(true); setError(""); try { setJob(await client.commitSimulationImport(jobId, preview.manifest_sha256)); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } };
  const exportJob = async () => { setBusy(true); setError(""); try { setJob(await client.exportSimulationJob(jobId)); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } };
  const retryJob = async () => { setBusy(true); setError(""); try { setJob(await client.retrySimulationJob(jobId)); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } };
  return <>
    <header className="page-header"><div><p className="eyebrow">Simulation job / {job?.status ?? "loading"}</p><h1>Manual simulation job</h1><p className="page-description">Export a reproducible batch, run it in your simulator, then import the CSV result.</p></div>{job?.status === "created" || job?.status === "draft" ? <button className="button button--primary page-action" disabled={busy} onClick={() => void exportJob()}>Export simulation batch</button> : job?.status === "failed" && job.retryable ? <button className="button button--primary page-action" disabled={busy} onClick={() => void retryJob()}>Retry import</button> : null}</header>
    <div className="manual-callout"><strong>No automatic simulator execution</strong><p>CircuitPilot prepares files and verifies returned evidence; the engineering operator controls the simulator.</p></div>
    <ExperimentTimeline current={job?.status === "completed" ? "resimulated" : job?.status === "waiting_for_results" ? "exported" : "approved"} />
    {job ? <p className="record-line"><span>Adapter</span><code>{job.adapter_type}</code><span>Candidates</span><code>{job.candidate_ids?.join(", ") || "—"}</code></p> : null}
    {error ? <div className="error-state"><p>{error}</p></div> : null}
    <SimulationImportPanel file={file} preview={preview} busy={busy} onFile={setFile} onPreview={() => void previewImport()} onCommit={() => void commitImport()} />
  </>;
}
