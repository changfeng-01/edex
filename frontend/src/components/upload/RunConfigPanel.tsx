import { Settings2 } from "lucide-react";

export interface RunConfig {
  caseId: string;
  topology: string;
  circuitProfile: string;
  stageCount: string;
  outputNodePattern: string;
  generateCandidates: boolean;
  runLlmAnalysis: boolean;
}

interface RunConfigPanelProps {
  config: RunConfig;
  onChange: (config: RunConfig) => void;
}

export function RunConfigPanel({ config, onChange }: RunConfigPanelProps) {
  return (
    <section className="rounded-lg border border-white/10 bg-slate-950/70 p-5 shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-100">
          <Settings2 size={20} />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-50">运行配置</h2>
          <p className="text-sm text-slate-400">留空字段使用现有评估默认值。</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <TextField label="case_id" value={config.caseId} onChange={(caseId) => onChange({ ...config, caseId })} />
        <TextField label="topology" value={config.topology} onChange={(topology) => onChange({ ...config, topology })} />
        <TextField label="circuit_profile" value={config.circuitProfile} onChange={(circuitProfile) => onChange({ ...config, circuitProfile })} />
        <TextField label="stage_count" value={config.stageCount} onChange={(stageCount) => onChange({ ...config, stageCount })} inputMode="numeric" />
        <TextField
          label="output_node_pattern"
          value={config.outputNodePattern}
          onChange={(outputNodePattern) => onChange({ ...config, outputNodePattern })}
        />
        <label className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/55 px-3 py-3 text-sm text-slate-200">
          <span>生成候选参数</span>
          <input
            type="checkbox"
            checked={config.generateCandidates}
            onChange={(event) => onChange({ ...config, generateCandidates: event.currentTarget.checked })}
          />
        </label>
        <label className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/55 px-3 py-3 text-sm text-slate-200">
          <span>运行 LLM 参数分析</span>
          <input
            type="checkbox"
            checked={config.runLlmAnalysis}
            onChange={(event) => onChange({ ...config, runLlmAnalysis: event.currentTarget.checked })}
          />
        </label>
      </div>
    </section>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  inputMode?: "numeric";
  onChange: (value: string) => void;
}

function TextField({ label, value, inputMode, onChange }: TextFieldProps) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-2 block font-medium">{label}</span>
      <input
        className="w-full rounded-md border border-white/10 bg-slate-950/70 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-200/60"
        value={value}
        inputMode={inputMode}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </label>
  );
}

