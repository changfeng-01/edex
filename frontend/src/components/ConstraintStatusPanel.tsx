import { ListChecks } from "lucide-react";

import { formatValue } from "../lib/demoData";
import type { ConstraintRow } from "../types";
import { StatusBadge } from "./StatusBadge";

interface ConstraintStatusPanelProps {
  rows?: ConstraintRow[];
}

const countKeys = ["pass", "fail", "unknown", "missing"] as const;
const countLabels: Record<(typeof countKeys)[number], string> = {
  pass: "通过",
  fail: "失败",
  unknown: "未知",
  missing: "缺失",
};

export function ConstraintStatusPanel({ rows = [] }: ConstraintStatusPanelProps) {
  const counts = countKeys.reduce(
    (acc, key) => ({
      ...acc,
      [key]: rows.filter((row) => (row.status || "unknown").toLowerCase() === key).length,
    }),
    {} as Record<(typeof countKeys)[number], number>,
  );

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="约束状态">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <ListChecks size={17} />
            约束状态
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">硬约束检查</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {countKeys.map((key) => (
            <span key={key} className="rounded-full border border-white/10 bg-slate-950/55 px-3 py-1 text-sm text-slate-200">
              {countLabels[key]}: <strong>{counts[key]}</strong>
            </span>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState message="dashboard_tables.json 中缺少约束表。" />
      ) : (
        <div className="mt-5 overflow-x-auto">
          <table className="min-w-[860px] w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase text-slate-400">
                <th className="py-3 pr-4">约束项</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">当前值</th>
                <th className="px-4 py-3">阈值</th>
                <th className="py-3 pl-4">原因</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.constraint}-${index}`} className="border-b border-white/5 transition-colors hover:bg-white/[0.04]">
                  <td className="py-3 pr-4 font-medium text-slate-100">{row.constraint}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.current_value)}</td>
                  <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.threshold)}</td>
                  <td className="py-3 pl-4 text-slate-300">{row.reason || "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="mt-5 rounded-lg border border-dashed border-slate-500/40 bg-slate-950/45 p-6 text-sm text-slate-400">
      {message}
    </div>
  );
}
