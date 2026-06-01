import { Activity, Layers3 } from "lucide-react";

import { StatusBadge } from "./StatusBadge";
import type { DashboardSummary } from "../types";

interface HeaderProps {
  summary: DashboardSummary;
}

export function Header({ summary }: HeaderProps) {
  return (
    <header className="rounded-lg border border-cyan-300/15 bg-slate-950/80 p-5 shadow-2xl shadow-black/25 backdrop-blur">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-cyan-200">
            <Layers3 size={16} />
            <span>EDA 工程证据仪表盘</span>
          </div>
          <h1 className="mt-3 text-4xl font-black leading-tight text-slate-50 md:text-6xl">CircuitPilot 演示仪表盘</h1>
          <div className="mt-4 flex flex-wrap gap-2 text-sm text-slate-300">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">case_id: {summary.case_id}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">run_id: {summary.run_id ?? "N/A"}</span>
            <span className="rounded-full border border-amber-300/35 bg-amber-300/10 px-3 py-1 text-amber-100">
              仿真证据包，仅限 simulation_only
            </span>
          </div>
        </div>

        <div className="grid gap-3 rounded-lg border border-white/10 bg-white/[0.04] p-4 sm:min-w-80">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Activity size={16} className="text-cyan-200" />
            当前展示状态
          </div>
          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-400">验证状态</span>
              <StatusBadge status={summary.validation_status} emphasis="strong" />
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-400">候选状态</span>
              <StatusBadge status={summary.candidate_status} emphasis="strong" />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
