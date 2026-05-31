import { Route } from "lucide-react";

import type { CandidateRow } from "../types";
import { formatValue } from "../lib/demoData";
import { StatusBadge } from "./StatusBadge";

interface CandidateRankingTableProps {
  rows?: CandidateRow[];
}

export function CandidateRankingTable({ rows = [] }: CandidateRankingTableProps) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-5" aria-label="Candidate Ranking">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-cyan-200">
            <Route size={17} />
            Candidate Ranking
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">Candidate recommendations for rerun</h2>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-400">
          Candidate entries show recommendation state only. They require rerun evidence before any validation conclusion.
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="mt-5 rounded-lg border border-dashed border-slate-500/40 bg-slate-950/45 p-6 text-sm text-slate-400">
          top_candidates_table is missing from dashboard_tables.json
        </div>
      ) : (
        <div className="mt-5 overflow-x-auto">
          <table className="min-w-[1080px] w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase text-slate-400">
                <th className="py-3 pr-4">rank</th>
                <th className="px-4 py-3">candidate_id</th>
                <th className="px-4 py-3">parameter_changes</th>
                <th className="px-4 py-3">trigger_metric</th>
                <th className="px-4 py-3">strategy</th>
                <th className="px-4 py-3">search_score</th>
                <th className="px-4 py-3">status</th>
                <th className="px-4 py-3">data_source</th>
                <th className="py-3 pl-4">engineering_validity</th>
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
