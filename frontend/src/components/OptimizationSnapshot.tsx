import { Bot, Database, GitBranch } from "lucide-react";

import { toFixedNumber, toPercent } from "../data/loaders";
import type { OptimizationRow, ScoreSummary } from "../types";

export function OptimizationSnapshot({
  rows,
  score,
}: {
  rows: OptimizationRow[];
  score: ScoreSummary;
}) {
  return (
    <section className="section-block" aria-label="参数与优化">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Parameter workflow</span>
          <h2>参数搜索快照</h2>
        </div>
        <span className="muted-label">optimization_dataset.csv</span>
      </div>

      <div className="optimization-layout">
        <div className="optimization-table">
          <div className="table-row table-head">
            <span>Run</span>
            <span>Status</span>
            <span>Score</span>
            <span>Overlap</span>
            <span>Boundary</span>
          </div>
          {rows.map((row) => (
            <div className="table-row" key={row.runId}>
              <span>{row.runId}</span>
              <strong>{row.status}</strong>
              <span>{toFixedNumber(row.score, 1)}</span>
              <span>{toPercent(row.maxOverlapRatio)}</span>
              <span>{row.engineeringValidity}</span>
            </div>
          ))}
        </div>

        <div className="workflow-panel">
          <div>
            <Database size={20} />
            <span>结构化指标已沉淀为固定 schema。</span>
          </div>
          <div>
            <GitBranch size={20} />
            <span>下一轮优先围绕 overlap 失效做候选仿真。</span>
          </div>
          <div>
            <Bot size={20} />
            <span>DeepSeek 分析层可读取候选表并生成解释，但不替代硬约束。</span>
          </div>
          <p>{score.warning_reasons.join(" / ")}</p>
        </div>
      </div>
    </section>
  );
}
