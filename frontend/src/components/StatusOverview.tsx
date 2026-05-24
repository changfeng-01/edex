import { Activity, AlertTriangle, CheckCircle2, Gauge, RadioTower, ShieldAlert } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { toFixedNumber, toPercent, toSecondsAsMicroseconds } from "../data/loaders";
import type { RealSummary, ScoreSummary } from "../types";

interface StatusOverviewProps {
  summary: RealSummary;
  score: ScoreSummary;
}

export function CommandScreen({ summary, score }: StatusOverviewProps) {
  const scoreValue = Math.round(score.overall_score ?? 0);
  const hardFailed = !score.hard_constraint_passed;
  const primaryFailure = score.hard_constraint_failures[0] ?? "No hard constraint failure";

  return (
    <section className="command-screen" aria-label="16:9 展示大屏">
      <div className="scanline" aria-hidden="true" />
      <header className="command-topbar">
        <div>
          <p className="eyebrow">Simulation command screen</p>
          <h1>CircuitPilot / 芯智调参</h1>
        </div>
        <div className="topbar-meta" aria-label="数据边界">
          <span>{summary.data_source}</span>
          <span>{summary.engineering_validity}</span>
          <span>{summary.run_timestamp}</span>
        </div>
      </header>

      <div className="command-grid">
        <div className="command-copy">
          <div className="status-line">
            <span className={hardFailed ? "status-mark failed" : "status-mark passed"}>{summary.Overall_status}</span>
            <span className="run-id">{summary.run_id}</span>
          </div>
          <p className="boundary-note">
            当前页面只展示仿真 CSV 产生的结构化分析结果，不是实物测试结论，也不代表自动优化闭环已经完成。
          </p>
          <div className="quick-facts">
            <span>{summary.stage_count} stages</span>
            <span>worst stage {summary.worst_stage ?? "N/A"}</span>
            <span>first failed {summary.first_failed_stage ?? "N/A"}</span>
          </div>
          <div className="risk-brief">
            <div>
              <span>Overlap risk</span>
              <strong>{toPercent(summary.Max_overlap_ratio)}</strong>
            </div>
            <p>{primaryFailure}</p>
          </div>
        </div>

        <div className="waveform-stage">
          <div className="screen-chrome">
            <span>Main waveform</span>
            <span>o1 / o8 comparison</span>
          </div>
          <img src="/data/figures/o1_o8_overview.png" alt="o1 到 o8 主输出波形" />
        </div>

        <div className="score-panel panel">
          <div className="score-ring" style={{ "--score": scoreValue } as CSSProperties}>
            <span>{scoreValue}</span>
          </div>
          <div>
            <div className="section-kicker">
              <Gauge size={16} />
              Overall score
            </div>
            <p>硬约束未完全通过，当前优先级是复核级间重叠窗口。</p>
          </div>
        </div>

        <div className="command-metrics">
          <MetricTile icon={<ShieldAlert size={18} />} label="Max overlap" value={toPercent(summary.Max_overlap_ratio)} tone="risk" />
          <MetricTile icon={<RadioTower size={18} />} label="Delay mean" value={toSecondsAsMicroseconds(summary.Delay_mean)} />
          <MetricTile icon={<Activity size={18} />} label="Max ripple" value={`${toFixedNumber(summary.Max_ripple, 3)} V`} />
          <MetricTile icon={<CheckCircle2 size={18} />} label="False trigger" value={`${summary.FalseTriggerCount}`} tone="ok" />
        </div>
      </div>
    </section>
  );
}

export function StatusOverview({ summary, score }: StatusOverviewProps) {
  const scoreValue = Math.round(score.overall_score ?? 0);
  const hardFailed = !score.hard_constraint_passed;
  return (
    <section className="status-grid" aria-label="状态总览">
      <div className="status-primary panel">
        <div className="section-kicker">
          <Activity size={16} />
          Current run
        </div>
        <div className="status-line">
          <span className={hardFailed ? "status-mark failed" : "status-mark passed"}>{summary.Overall_status}</span>
          <span className="run-id">{summary.run_id}</span>
        </div>
        <p className="boundary-note">
          当前页面只展示仿真 CSV 产生的结构化分析结果，不是实物测试结论，也不代表自动优化闭环已经完成。
        </p>
        <div className="quick-facts">
          <span>{summary.stage_count} stages</span>
          <span>{summary.data_source}</span>
          <span>{summary.engineering_validity}</span>
        </div>
      </div>

      <div className="score-panel panel">
        <div className="score-ring" style={{ "--score": scoreValue } as CSSProperties}>
          <span>{scoreValue}</span>
        </div>
        <div>
          <div className="section-kicker">
            <Gauge size={16} />
            Overall score
          </div>
          <p>硬约束未完全通过，当前优先级是复核级间重叠窗口。</p>
        </div>
      </div>

      <MetricTile icon={<ShieldAlert size={18} />} label="Max overlap" value={toPercent(summary.Max_overlap_ratio)} tone="risk" />
      <MetricTile icon={<RadioTower size={18} />} label="Delay mean" value={toSecondsAsMicroseconds(summary.Delay_mean)} />
      <MetricTile icon={<Activity size={18} />} label="Max ripple" value={`${toFixedNumber(summary.Max_ripple, 3)} V`} />
      <MetricTile icon={<CheckCircle2 size={18} />} label="False trigger" value={`${summary.FalseTriggerCount}`} tone="ok" />
    </section>
  );
}

function MetricTile({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "neutral" | "risk" | "ok";
}) {
  return (
    <div className={`metric-tile panel ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function ActionStrip({ score }: { score: ScoreSummary }) {
  const primaryFailure = score.hard_constraint_failures[0] ?? "No hard constraint failure";
  return (
    <section className="action-strip">
      <div>
        <div className="section-kicker">
          <AlertTriangle size={16} />
          Next action
        </div>
        <h2>先复核 overlap，再进入下一轮候选参数仿真。</h2>
      </div>
      <p>{primaryFailure}</p>
    </section>
  );
}
