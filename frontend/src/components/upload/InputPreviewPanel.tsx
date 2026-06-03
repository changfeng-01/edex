import { AlertTriangle, CheckCircle2, Image, ListChecks } from "lucide-react";

type EvidenceBoundary = {
  data_source?: string;
  engineering_validity?: string;
  must_resimulate?: boolean;
};

type ParamsSummary = {
  exists?: boolean;
  parameter_count?: number;
  parameter_names?: string[];
  has_param_space?: boolean;
};

type NetlistSummary = {
  netlist_available?: boolean;
  mos_like_device_count?: number;
  capacitor_like_count?: number;
  resistor_like_count?: number;
  subckt_count?: number;
};

type AttachmentsSummary = {
  image_count?: number;
  image_analysis_enabled?: boolean;
};

export type InputPreview = {
  ready_for_analysis?: boolean;
  row_count?: number;
  column_count?: number;
  time_column_original?: string | null;
  time_min?: number | null;
  time_max?: number | null;
  time_span?: number | null;
  guessed_time_unit?: string | null;
  voltage_min?: number | null;
  voltage_max?: number | null;
  detected_output_node_count?: number;
  sample_output_nodes?: string[];
  missing_configured_nodes?: string[];
  params_summary?: ParamsSummary;
  netlist_summary?: NetlistSummary;
  attachments_summary?: AttachmentsSummary;
  warnings?: string[];
  errors?: string[];
  suggestions?: string[];
};

interface InputPreviewPanelProps {
  preview: InputPreview;
  evidenceBoundary?: EvidenceBoundary;
}

export function InputPreviewPanel({ preview, evidenceBoundary }: InputPreviewPanelProps) {
  const params = preview.params_summary ?? {};
  const netlist = preview.netlist_summary ?? {};
  const attachments = preview.attachments_summary ?? {};
  const ready = preview.ready_for_analysis === true;

  return (
    <section className="rounded-lg border border-cyan-300/15 bg-slate-950/70 p-5 shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3">
        <div className={`grid h-10 w-10 place-items-center rounded-lg border ${ready ? "border-emerald-200/25 bg-emerald-300/10 text-emerald-100" : "border-amber-200/25 bg-amber-300/10 text-amber-100"}`}>
          {ready ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-50">Input Preview</h2>
          <p className={ready ? "text-sm text-emerald-100" : "text-sm text-amber-100"}>
            {ready ? "Ready for analysis / 可进入分析" : "Needs input fixes / 需要修正输入"}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 text-sm text-slate-300">
        <MetricGrid
          items={[
            ["Rows", formatValue(preview.row_count)],
            ["Columns", formatValue(preview.column_count)],
            ["Time column", preview.time_column_original || "not detected"],
            ["Time range", `${formatValue(preview.time_min)} to ${formatValue(preview.time_max)}`],
            ["Time span", formatValue(preview.time_span)],
            ["Guessed unit", preview.guessed_time_unit || "unknown"],
            ["Voltage range", `${formatValue(preview.voltage_min)} to ${formatValue(preview.voltage_max)}`],
          ]}
        />

        <div className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
          <div className="flex items-center gap-2 font-semibold text-slate-100">
            <ListChecks size={16} />
            Output nodes
          </div>
          <p className="mt-2">Detected output node count: {formatValue(preview.detected_output_node_count)}</p>
          <p className="mt-1">Sample nodes: {(preview.sample_output_nodes ?? []).join(", ") || "none"}</p>
          {(preview.missing_configured_nodes ?? []).length > 0 ? (
            <p className="mt-2 text-amber-100">配置要求的部分节点未找到: {preview.missing_configured_nodes?.join(", ")}</p>
          ) : null}
        </div>

        <MetricGrid
          items={[
            ["params.yaml", params.exists ? "available" : "not uploaded"],
            ["Parameter count", formatValue(params.parameter_count)],
            ["Parameter names", (params.parameter_names ?? []).slice(0, 8).join(", ") || "none"],
            ["Has parameter space", params.has_param_space ? "yes" : "no"],
            ["Netlist", netlist.netlist_available ? "available" : "not uploaded"],
            ["MOS-like", formatValue(netlist.mos_like_device_count)],
            ["Capacitor-like", formatValue(netlist.capacitor_like_count)],
            ["Resistor-like", formatValue(netlist.resistor_like_count)],
            ["Subckt", formatValue(netlist.subckt_count)],
          ]}
        />

        <div className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
          <div className="flex items-center gap-2 font-semibold text-slate-100">
            <Image size={16} />
            Attachments
          </div>
          <p className="mt-2">Image count: {formatValue(attachments.image_count)}</p>
          <p className="mt-1 text-slate-400">图片当前只作为附件展示，不参与曲线识别。</p>
        </div>

        <MessageList title="Warnings" items={preview.warnings ?? []} tone="warning" />
        <MessageList title="Errors" items={preview.errors ?? []} tone="error" />
        <MessageList title="Suggestions" items={preview.suggestions ?? []} tone="neutral" />

        <div className="rounded-lg border border-amber-300/20 bg-amber-300/10 p-4 text-amber-50">
          <div className="font-semibold">Evidence boundary</div>
          <p className="mt-2">data_source = {evidenceBoundary?.data_source ?? "real_simulation_csv"}</p>
          <p>engineering_validity = {evidenceBoundary?.engineering_validity ?? "simulation_only"}</p>
          <p>must_resimulate = {String(evidenceBoundary?.must_resimulate ?? true)}</p>
        </div>
      </div>
    </section>
  );
}

function MetricGrid({ items }: { items: [string, string][] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-white/10 bg-slate-950/50 px-3 py-2">
          <div className="text-xs uppercase text-slate-500">{label}</div>
          <div className="mt-1 break-words text-slate-100">{value}</div>
        </div>
      ))}
    </div>
  );
}

function MessageList({ title, items, tone }: { title: string; items: string[]; tone: "warning" | "error" | "neutral" }) {
  if (items.length === 0) {
    return null;
  }
  const toneClass =
    tone === "error"
      ? "border-rose-300/25 bg-rose-300/10 text-rose-50"
      : tone === "warning"
        ? "border-amber-300/25 bg-amber-300/10 text-amber-50"
        : "border-white/10 bg-slate-950/50 text-slate-200";
  return (
    <div className={`rounded-lg border p-4 ${toneClass}`}>
      <div className="font-semibold">{title}</div>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toPrecision(4).replace(/\.?0+$/, "") : "n/a";
  }
  return String(value);
}
