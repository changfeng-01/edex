import { GitCompareArrows } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatStatusLabel, formatValue, hasAfterValue, toNumber } from "../lib/demoData";
import type { BeforeAfterRow } from "../types";
import { StatusBadge } from "./StatusBadge";

interface BeforeAfterPanelProps {
  rows?: BeforeAfterRow[];
}

export function BeforeAfterPanel({ rows = [] }: BeforeAfterPanelProps) {
  const chartRows = rows
    .filter((row) => hasAfterValue(row.after_value))
    .map((row) => ({
      metric: row.metric,
      before: toNumber(row.before_value),
      after: toNumber(row.after_value),
    }))
    .filter((row) => row.before !== null && row.after !== null);

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="重跑前后对比">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <GitCompareArrows size={17} />
            重跑前后对比
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">重跑验证状态</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">
          只有数据包中存在 after-run 数值时，才会展示前后对比图。
        </p>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_0.85fr]">
        <div className="overflow-x-auto">
          <table className="min-w-[760px] w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase text-slate-400">
                <th className="py-3 pr-4">指标</th>
                <th className="px-4 py-3">重跑前</th>
                <th className="px-4 py-3">重跑后</th>
                <th className="px-4 py-3">变化量</th>
                <th className="px-4 py-3">状态</th>
                <th className="py-3 pl-4">单位</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-slate-400">
                    dashboard_tables.json 中缺少重跑前后对比表。
                  </td>
                </tr>
              ) : (
                rows.map((row, index) => (
                  <tr key={`${row.metric}-${index}`} className="border-b border-white/5 transition-colors hover:bg-white/[0.04]">
                    <td className="py-3 pr-4 font-medium text-slate-100">{row.metric}</td>
                    <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.before_value)}</td>
                    <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.after_value)}</td>
                    <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.delta)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="py-3 pl-4 text-slate-300">{row.unit || "N/A"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="min-h-72 rounded-lg border border-white/10 bg-slate-950/55 p-4">
          {chartRows.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartRows}>
                <CartesianGrid stroke="rgba(148, 163, 184, 0.18)" vertical={false} />
                <XAxis dataKey="metric" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.14)" }} />
                <Legend />
                <Bar dataKey="before" fill="#67e8f9" name="重跑前" radius={[4, 4, 0, 0]} />
                <Bar dataKey="after" fill="#fbbf24" name="重跑后" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full min-h-64 place-items-center rounded-lg border border-dashed border-amber-300/30 bg-amber-300/[0.06] p-6 text-center">
              <div>
                <div className="text-lg font-semibold text-amber-100">尚未生成 after-run 结果</div>
                <p className="mt-2 text-sm text-amber-100/75">
                  当前状态：{formatStatusLabel(rows[0]?.status ?? "awaiting_rerun_results")}。因此不渲染前后对比图。
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
