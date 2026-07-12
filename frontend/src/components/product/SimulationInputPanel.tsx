import { useRef, useState } from "react";

import { createProductClient } from "../../api/productClient";
import type { AnalysisRun, InputSnapshot } from "../../types/product";
import { ErrorState } from "./ErrorState";

export interface AnalysisContext {
  versionId: string;
  circuitProfile?: string;
}

interface SimulationInputPanelProps {
  validateContext?: () => boolean;
  resolveContext: () => Promise<AnalysisContext | null>;
  onContextLocked?: (context: AnalysisContext) => void;
  onAnalysisCreated: (run: AnalysisRun) => void;
}

type WorkflowState =
  | "idle"
  | "creating_context"
  | "previewing"
  | "preview_ready"
  | "preview_ready_with_warnings"
  | "analyzing"
  | "preview_failed"
  | "analysis_failed";

export function SimulationInputPanel({ validateContext, resolveContext, onContextLocked, onAnalysisCreated }: SimulationInputPanelProps) {
  const client = createProductClient();
  const contextRef = useRef<AnalysisContext | null>(null);
  const [waveform, setWaveform] = useState<File>();
  const [params, setParams] = useState<File>();
  const [netlist, setNetlist] = useState<File>();
  const [attachments, setAttachments] = useState<File[]>([]);
  const [snapshot, setSnapshot] = useState<InputSnapshot>();
  const [workflowState, setWorkflowState] = useState<WorkflowState>("idle");
  const [error, setError] = useState<unknown>();
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({});
  const [topology, setTopology] = useState("");
  const [stageCount, setStageCount] = useState("");
  const [outputPattern, setOutputPattern] = useState("o{index}");
  const [generateSuggestions, setGenerateSuggestions] = useState(true);
  const [runLlm, setRunLlm] = useState(false);

  const busy = ["creating_context", "previewing", "analyzing"].includes(workflowState);

  function invalidatePreview() {
    setSnapshot(undefined);
    setError(undefined);
    setWorkflowState("idle");
  }

  function validateFiles() {
    const next: Record<string, string> = {};
    if (!waveform) next.waveform = "Waveform CSV is required.";
    if (!params) next.params = "Parameter YAML is required.";
    setFileErrors(next);
    return Object.keys(next).length === 0;
  }

  async function preview() {
    const contextIsValid = validateContext?.() ?? true;
    const filesAreValid = validateFiles();
    if (!contextIsValid || !filesAreValid || !waveform || !params) return;
    setError(undefined);
    try {
      let context = contextRef.current;
      if (!context) {
        setWorkflowState("creating_context");
        context = await resolveContext();
        if (!context) {
          setWorkflowState("idle");
          return;
        }
        contextRef.current = context;
        onContextLocked?.(context);
      }
      setWorkflowState("previewing");
      const form = new FormData();
      form.append("waveform", waveform);
      form.append("params", params);
      if (netlist) form.append("netlist", netlist);
      attachments.forEach((attachment) => form.append("attachments", attachment));
      const nextSnapshot = await client.previewInput(context.versionId, form);
      setSnapshot(nextSnapshot);
      const warnings = nextSnapshot.preview.warnings ?? [];
      if (nextSnapshot.preview_status === "preview_ready_with_warnings" || warnings.length > 0) {
        setWorkflowState("preview_ready_with_warnings");
        return;
      }
      setWorkflowState("preview_ready");
      await runAnalysis(nextSnapshot, context);
    } catch (nextError) {
      setError(nextError);
      setSnapshot(undefined);
      setWorkflowState("preview_failed");
    }
  }

  async function runAnalysis(nextSnapshot = snapshot, context = contextRef.current) {
    if (!nextSnapshot || !context) return;
    setError(undefined);
    setWorkflowState("analyzing");
    try {
      const run = await client.createAnalysis(context.versionId, {
        input_manifest_ref: nextSnapshot.manifest_ref,
        case_id: `product_${context.versionId}`,
        circuit_profile: context.circuitProfile || undefined,
        topology: topology.trim() || undefined,
        stage_count: stageCount ? Number(stageCount) : undefined,
        output_node_pattern: outputPattern || "o{index}",
        generate_readonly_suggestions: generateSuggestions,
        run_llm_analysis: runLlm,
      });
      onAnalysisCreated(run);
    } catch (nextError) {
      setError(nextError);
      setWorkflowState("analysis_failed");
    }
  }

  return (
    <div className="simulation-input">
      <div className="input-file-grid">
        <FileField
          label="Waveform CSV"
          accept=".csv,text/csv"
          selected={waveform}
          error={fileErrors.waveform}
          onChange={(file) => { setWaveform(file); setFileErrors((current) => ({ ...current, waveform: "" })); invalidatePreview(); }}
        />
        <FileField
          label="Parameter YAML"
          accept=".yaml,.yml,application/yaml,text/yaml"
          selected={params}
          error={fileErrors.params}
          onChange={(file) => { setParams(file); setFileErrors((current) => ({ ...current, params: "" })); invalidatePreview(); }}
        />
        <FileField
          label="Netlist (optional)"
          accept=".sp,.spice,.netlist"
          selected={netlist}
          onChange={(file) => { setNetlist(file); invalidatePreview(); }}
        />
        <label className="input-file-field">
          <span>Plot images (optional)</span>
          <input
            aria-label="Plot images"
            type="file"
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            multiple
            onChange={(event) => { setAttachments(Array.from(event.target.files ?? [])); invalidatePreview(); }}
          />
          <small>{attachments.length ? `${attachments.length} image${attachments.length > 1 ? "s" : ""} selected` : "PNG or JPG · multiple allowed"}</small>
        </label>
      </div>

      <details className="advanced-settings">
        <summary>Advanced settings</summary>
        <div className="advanced-grid">
          <label>Topology<input aria-label="Topology" value={topology} onChange={(event) => setTopology(event.target.value)} placeholder="Optional" /></label>
          <label>Stage count<input aria-label="Stage count" type="number" min="1" value={stageCount} onChange={(event) => setStageCount(event.target.value)} placeholder="Optional" /></label>
          <label>Output node pattern<input aria-label="Output node pattern" value={outputPattern} onChange={(event) => setOutputPattern(event.target.value)} /></label>
          <label className="check-field"><input type="checkbox" checked={generateSuggestions} onChange={(event) => setGenerateSuggestions(event.target.checked)} />Generate read-only candidates</label>
          <label className="check-field"><input type="checkbox" checked={runLlm} onChange={(event) => setRunLlm(event.target.checked)} />Run LLM analysis</label>
        </div>
      </details>

      {workflowState === "preview_ready_with_warnings" ? (
        <div className="warning" role="status"><strong>Preview warning</strong>{snapshot?.preview.warnings?.map((warning) => <p key={warning}>{warning}</p>)}</div>
      ) : null}
      {workflowState === "preview_failed" ? <div className="workflow-error"><h3>Preview failed</h3><ErrorState error={error} compact /></div> : null}
      {workflowState === "analysis_failed" ? <div className="workflow-error"><h3>Analysis failed</h3><ErrorState error={error} compact /></div> : null}

      <div className="upload-actions">
        <button className="button button--primary" disabled={busy} onClick={preview}>
          {workflowState === "preview_failed" ? "Retry preview" : workflowState === "creating_context" ? "Creating context…" : workflowState === "previewing" ? "Previewing…" : "Preview input"}
        </button>
        {workflowState === "preview_ready_with_warnings" ? <button className="button" onClick={() => runAnalysis()}>Confirm and run</button> : null}
        {workflowState === "analysis_failed" ? <button className="button" onClick={() => runAnalysis()}>Retry analysis</button> : null}
        {workflowState === "analyzing" ? <span className="workflow-status">Creating analysis run…</span> : null}
      </div>
    </div>
  );
}

function FileField({ label, accept, selected, error, onChange }: { label: string; accept: string; selected?: File; error?: string; onChange: (file?: File) => void }) {
  return (
    <label className={`input-file-field${error ? " input-file-field--error" : ""}`}>
      <span>{label}</span>
      <input aria-label={label} type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0])} />
      <small>{selected ? `${selected.name} selected` : "No file selected"}</small>
      {error ? <em>{error}</em> : null}
    </label>
  );
}
