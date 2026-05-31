import { CheckCircle2, Gauge, Hash, ShieldCheck, Workflow } from "lucide-react";

import { formatValue } from "../lib/demoData";
import type { DashboardSummary } from "../types";
import { StatusBadge } from "./StatusBadge";

interface OverviewCardsProps {
  summary: DashboardSummary;
}

export function OverviewCards({ summary }: OverviewCardsProps) {
  const items = [
    { label: "case_id", value: summary.case_id, icon: <Hash size={17} /> },
    { label: "run_id", value: summary.run_id ?? "N/A", icon: <Workflow size={17} /> },
    { label: "overall_status", value: summary.overall_status ?? "N/A", icon: <Gauge size={17} /> },
    { label: "overall_score", value: formatValue(summary.overall_score), icon: <Gauge size={17} /> },
  ];

  return (
    <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]" aria-label="Overview">
      <div className="rounded-lg border border-white/10 bg-white/[0.04] p-5">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
          <ShieldCheck size={17} />
          Overview
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((item) => (
            <div key={item.label} className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-slate-400">
                <span className="text-cyan-200">{item.icon}</span>
                {item.label}
              </div>
              <div className="mt-3 break-words text-xl font-bold text-slate-50">{item.value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 rounded-lg border border-white/10 bg-white/[0.04] p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-cyan-200">Hard constraint</div>
            <p className="mt-1 text-sm text-slate-400">The dashboard reports pass state from product-demo data only.</p>
          </div>
          <CheckCircle2 className="text-cyan-200" size={28} />
        </div>
        <div className="grid gap-3">
          <StatusRow label="hard_constraint_passed" value={summary.hard_constraint_passed} />
          <StatusRow label="validation_status" value={summary.validation_status} />
          <StatusRow label="candidate_status" value={summary.candidate_status} />
        </div>
      </div>
    </section>
  );
}

function StatusRow({ label, value }: { label: string; value?: string | boolean | number | null }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-slate-950/55 px-4 py-3">
      <span className="min-w-0 text-sm text-slate-300">{label}</span>
      <StatusBadge status={value} emphasis="strong" />
    </div>
  );
}
