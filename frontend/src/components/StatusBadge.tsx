import { formatStatusLabel } from "../lib/demoData";

interface StatusBadgeProps {
  status?: string | boolean | number | null;
  emphasis?: "normal" | "strong";
}

const toneClasses: Record<string, string> = {
  pass: "border-emerald-400/40 bg-emerald-400/12 text-emerald-200",
  fail: "border-red-400/45 bg-red-400/12 text-red-200",
  missing: "border-slate-400/35 bg-slate-400/10 text-slate-300",
  unknown: "border-slate-400/35 bg-slate-400/10 text-slate-300",
  awaiting_rerun_results: "border-amber-300/45 bg-amber-300/12 text-amber-100",
  ready_for_rerun: "border-amber-300/45 bg-amber-300/12 text-amber-100",
  awaiting_candidate_generation: "border-sky-300/45 bg-sky-300/12 text-sky-100",
  available: "border-cyan-300/40 bg-cyan-300/12 text-cyan-100",
  true: "border-emerald-400/40 bg-emerald-400/12 text-emerald-200",
  false: "border-red-400/45 bg-red-400/12 text-red-200",
};

export function StatusBadge({ status, emphasis = "normal" }: StatusBadgeProps) {
  const raw = String(status ?? "unknown");
  const normalized = raw.trim();
  const key = normalized.toLowerCase();
  const classes = toneClasses[key] ?? "border-cyan-300/25 bg-white/5 text-slate-200";
  const label = typeof status === "boolean" ? (status ? "是" : "否") : formatStatusLabel(normalized);

  return (
    <span
      className={[
        "inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-xs font-semibold leading-none",
        emphasis === "strong" ? "uppercase tracking-wide" : "",
        classes,
      ].join(" ")}
      title={normalized}
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
