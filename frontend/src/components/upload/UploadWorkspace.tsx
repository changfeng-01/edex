import { useState } from "react";
import { Eye, Play, ShieldAlert, Sparkles } from "lucide-react";

import { AnalysisProgress } from "./AnalysisProgress";
import { FileDropzone, type UploadFiles } from "./FileDropzone";
import { InputPreviewPanel, type InputPreview } from "./InputPreviewPanel";
import { RunConfigPanel, type RunConfig } from "./RunConfigPanel";
import { UploadedFileList } from "./UploadedFileList";

interface UploadWorkspaceProps {
  apiBaseUrl: string;
  onCaseCreated?: (caseId: string) => void;
}

const initialFiles: UploadFiles = {
  waveform: null,
  params: null,
  netlist: null,
  attachments: [],
};

const initialConfig: RunConfig = {
  caseId: "",
  topology: "",
  circuitProfile: "",
  stageCount: "",
  outputNodePattern: "o{index}",
  generateCandidates: true,
  runLlmAnalysis: false,
};

export function UploadWorkspace({ apiBaseUrl, onCaseCreated }: UploadWorkspaceProps) {
  const [files, setFiles] = useState<UploadFiles>(initialFiles);
  const [config, setConfig] = useState<RunConfig>(initialConfig);
  const [status, setStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [message, setMessage] = useState("");
  const [inputPreview, setInputPreview] = useState<InputPreview | null>(null);
  const [previewEvidenceBoundary, setPreviewEvidenceBoundary] = useState<Record<string, unknown> | undefined>();

  async function runBuiltInDemo() {
    setStatus("running");
    setMessage("正在运行内置 examples/sample_waveform.csv 和 examples/sample_params.yaml 演示...");
    try {
      const response = await fetch(`${apiBaseUrl}/api/demo/sample-case`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok || payload.status === "failed") {
        throw new Error(payload.detail || payload.error || `API returned ${response.status}`);
      }
      completeCase(payload.case_id, "内置演示分析完成，正在进入 dashboard。");
    } catch (error) {
      setStatus("failed");
      setMessage(`内置演示运行失败：${String(error)}`);
    }
  }

  async function submit() {
    if (!files.waveform) {
      setStatus("failed");
      setMessage("请先上传 waveform.csv。");
      return;
    }
    setStatus("running");
    setMessage("正在保存文件并运行仿真 CSV 评价...");
    const form = buildUploadForm(files, config);

    try {
      const response = await fetch(`${apiBaseUrl}/api/cases`, { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok || payload.status === "failed") {
        throw new Error(payload.detail || payload.error || `API returned ${response.status}`);
      }
      completeCase(payload.case_id, "分析完成，正在进入 dashboard。");
    } catch (error) {
      setStatus("failed");
      setMessage(`上传或分析失败：${String(error)}`);
    }
  }

  async function previewInput() {
    if (!files.waveform) {
      setStatus("failed");
      setMessage("Please upload waveform.csv before preview.");
      return;
    }
    setStatus("running");
    setMessage("Previewing uploaded input files...");
    const form = buildUploadForm(files, config);

    try {
      const response = await fetch(`${apiBaseUrl}/api/cases/preview`, { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || `API returned ${response.status}`);
      }
      setStatus("idle");
      setMessage(payload.preview?.ready_for_analysis ? "Input preview is ready. Run Analysis remains available." : "Input preview found issues. Run Analysis remains available for compatibility.");
      setInputPreview(payload.preview);
      setPreviewEvidenceBoundary(payload.evidence_boundary);
      if (payload.case_id) {
        setConfig((current) => ({ ...current, caseId: payload.case_id }));
        window.history.pushState(null, "", `?case_id=${encodeURIComponent(payload.case_id)}`);
      }
    } catch (error) {
      setStatus("failed");
      setMessage(`Input preview failed: ${String(error)}`);
    }
  }

  function completeCase(caseId: string, nextMessage: string) {
    setStatus("completed");
    setMessage(nextMessage);
    window.history.pushState(null, "", `?case_id=${encodeURIComponent(caseId)}`);
    onCaseCreated?.(caseId);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="dashboard-bg" aria-hidden="true" />
      <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-5 px-4 py-5 md:px-6 lg:px-8">
        <header className="rounded-lg border border-cyan-300/15 bg-slate-950/80 p-5 shadow-2xl shadow-black/25 backdrop-blur">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">CircuitPilot Upload-to-Dashboard</p>
          <h1 className="mt-3 text-2xl font-bold text-slate-50 md:text-3xl">Upload-to-Dashboard 工作区</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
            上传真实仿真 CSV 后同步生成波形评价、约束诊断、候选参数建议和 product-demo dashboard 数据包。
          </p>
        </header>

        <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr_0.8fr]">
          <div className="grid gap-5">
            <FileDropzone files={files} onFilesChange={setFiles} />
            <UploadedFileList files={files} />
          </div>
          <div className="grid content-start gap-5">
            <RunConfigPanel config={config} onChange={setConfig} />
            <div className="grid gap-3 sm:grid-cols-3">
              <button
                className="flex items-center justify-center gap-2 rounded-lg border border-cyan-200/30 bg-cyan-300/15 px-4 py-3 text-sm font-semibold text-cyan-50 transition hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={status === "running"}
                onClick={runBuiltInDemo}
              >
                <Sparkles size={18} />
                Run Built-in Demo
              </button>
              <button
                className="flex items-center justify-center gap-2 rounded-lg border border-emerald-200/30 bg-emerald-300/15 px-4 py-3 text-sm font-semibold text-emerald-50 transition hover:bg-emerald-300/20 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={status === "running"}
                onClick={previewInput}
              >
                <Eye size={18} />
                Preview Input
              </button>
              <button
                className="flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-slate-900/80 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-cyan-200/30 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                disabled={status === "running"}
                onClick={submit}
              >
                <Play size={18} />
                Run Analysis
              </button>
            </div>
            {inputPreview && inputPreview.ready_for_analysis === false ? (
              <div className="rounded-lg border border-amber-300/25 bg-amber-300/10 px-4 py-3 text-sm text-amber-50">
                Preview detected input issues. Run Analysis is still available, but review the panel first.
              </div>
            ) : null}
            <AnalysisProgress status={status} message={message} />
          </div>
          <aside className="rounded-lg border border-amber-300/20 bg-slate-950/70 p-5 shadow-2xl shadow-black/20">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-lg border border-amber-200/20 bg-amber-300/10 text-amber-100">
                <ShieldAlert size={20} />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-slate-50">说明与边界</h2>
                <p className="text-sm text-slate-400">上传结果只代表仿真证据。</p>
              </div>
            </div>
            <div className="mt-5 grid gap-3 text-sm leading-6 text-slate-300">
              <p>data_source = real_simulation_csv</p>
              <p>engineering_validity = simulation_only</p>
              <p>must_resimulate = true</p>
              <p>图片第一版只作为附件展示，不用于曲线识别。</p>
              <p>候选参数建议必须进入下一轮仿真验证；not physical or silicon validation。</p>
            </div>
          </aside>
        </div>
        {inputPreview ? <InputPreviewPanel preview={inputPreview} evidenceBoundary={previewEvidenceBoundary} /> : null}
      </div>
    </main>
  );
}

function buildUploadForm(files: UploadFiles, config: RunConfig) {
  const form = new FormData();
  if (files.waveform) {
    form.append("waveform", files.waveform);
  }
  if (files.params) {
    form.append("params", files.params);
  }
  if (files.netlist) {
    form.append("netlist", files.netlist);
  }
  for (const attachment of files.attachments) {
    form.append("attachments", attachment);
  }
  appendIfPresent(form, "case_id", config.caseId);
  appendIfPresent(form, "topology", config.topology);
  appendIfPresent(form, "circuit_profile", config.circuitProfile);
  appendIfPresent(form, "stage_count", config.stageCount);
  appendIfPresent(form, "output_node_pattern", config.outputNodePattern);
  form.append("generate_candidates", String(config.generateCandidates));
  form.append("run_llm_analysis", String(config.runLlmAnalysis));
  return form;
}

function appendIfPresent(form: FormData, key: string, value: string) {
  const trimmed = value.trim();
  if (trimmed) {
    form.append(key, trimmed);
  }
}
