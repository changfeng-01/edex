import { AlertTriangle, Cpu } from "lucide-react";

import { formatValue } from "../lib/demoData";
import type { EvidenceBoundary } from "../types";

interface EvidenceBoundaryCardProps {
  evidence?: EvidenceBoundary;
}

const evidenceFields: Array<keyof EvidenceBoundary> = [
  "data_source",
  "engineering_validity",
  "evidence_level",
  "simulation_backend",
  "mock_used",
  "optimizer_claim_level",
];

const evidenceFieldLabels: Record<keyof EvidenceBoundary, string> = {
  data_source: "数据来源",
  engineering_validity: "工程有效性",
  evidence_level: "证据等级",
  simulation_backend: "仿真后端",
  mock_used: "是否使用 mock",
  optimizer_claim_level: "优化器声明等级",
};

export function EvidenceBoundaryCard({ evidence }: EvidenceBoundaryCardProps) {
  const isSimulationOnly = evidence?.engineering_validity === "simulation_only";

  return (
    <section className="rounded-lg border border-amber-300/20 bg-amber-300/[0.06] p-5" aria-label="证据边界">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-amber-100">
            <Cpu size={17} />
            证据边界
          </div>
          <h2 className="mt-2 text-2xl font-bold text-slate-50">仿真与 CSV 证据边界</h2>
        </div>
        {isSimulationOnly ? (
          <div className="max-w-2xl rounded-lg border border-amber-300/30 bg-slate-950/60 p-4 text-sm leading-6 text-amber-50">
            <div className="mb-2 flex items-center gap-2 font-semibold">
              <AlertTriangle size={16} />
              当前结果为仿真 CSV 证据包，不代表物理验证、硅验证或流片验证。
            </div>
            <p className="m-0 text-amber-100/80">
              候选参数行仅代表下一轮重跑建议，不是已经完成的验证结果。
            </p>
          </div>
        ) : null}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {evidenceFields.map((field) => (
          <div key={field} className="rounded-lg border border-white/10 bg-slate-950/55 p-4">
            <div className="text-xs font-semibold uppercase text-slate-400">{evidenceFieldLabels[field]}</div>
            <div className="mt-2 break-words font-mono text-sm text-slate-100">{formatValue(evidence?.[field])}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
