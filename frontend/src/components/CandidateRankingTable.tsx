import { Route } from "lucide-react";

import type { CandidateRow } from "../types";
import { formatValue } from "../lib/demoData";
import { StatusBadge } from "./StatusBadge";

interface CandidateRankingTableProps {
  rows?: CandidateRow[];
}

export function CandidateRankingTable({ rows = [] }: CandidateRankingTableProps) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="候选参数排序">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <Route size={17} />
            候选参数排序
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">下一轮重跑候选建议</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">
          候选项只表示推荐状态，必须有重跑证据后才能形成验证结论。
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="mt-5 rounded-lg border border-dashed border-slate-500/40 bg-slate-950/45 p-6 text-sm text-slate-400">
          dashboard_tables.json 中缺少候选参数表。
        </div>
      ) : (
        <div className="mt-5 overflow-x-auto">
          <table className="min-w-[1080px] w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase text-slate-400">
                <th className="py-3 pr-4">排序</th>
                <th className="px-4 py-3">候选编号</th>
                <th className="px-4 py-3">参数变化</th>
                <th className="px-4 py-3">触发指标</th>
                <th className="px-4 py-3">策略</th>
                <th className="px-4 py-3">搜索分数</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">数据来源</th>
                <th className="py-3 pl-4">工程有效性</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.candidate_id ?? "candidate"}-${index}`} className="border-b border-white/5 transition-colors hover:bg-white/[0.04]">
                  <td className="py-3 pr-4 font-mono text-slate-200">{formatValue(row.rank)}</td>
                  <td className="px-4 py-3 font-medium text-slate-100">{row.candidate_id || "N/A"}</td>
                  <td className="max-w-xs px-4 py-3 text-slate-300">{row.parameter_changes || "N/A"}</td>
                  <td className="px-4 py-3 text-slate-300">{row.trigger_metric || "N/A"}</td>
                  <td className="px-4 py-3 text-slate-300">{row.strategy || "N/A"}</td>
                  <td className="px-4 py-3 font-mono text-slate-300">{formatValue(row.search_score)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{row.data_source || "N/A"}</td>
                  <td className="py-3 pl-4 font-mono text-xs text-slate-300">{row.engineering_validity || "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
