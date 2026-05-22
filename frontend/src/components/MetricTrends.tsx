import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";

import { formatMicroseconds, toPercent } from "../data/loaders";
import type { MetricRow } from "../types";

const chartFrame = {
  grid: "rgba(141, 245, 213, 0.14)",
  axis: "#8aa09a",
  panel: "rgba(8, 21, 19, 0.96)",
  border: "rgba(141, 245, 213, 0.22)",
};

export function MetricTrends({ metrics }: { metrics: MetricRow[] }) {
  return (
    <section className="section-block trend-section" aria-label="逐级指标趋势">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Stage metrics</span>
          <h2>逐级指标趋势</h2>
        </div>
        <span className="muted-label">VOH / Delay / Ripple / Overlap</span>
      </div>
      <div className="chart-grid">
        <ChartPanel title="VOH and ripple">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={metrics} margin={{ top: 12, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={chartFrame.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="node" tick={{ fill: chartFrame.axis }} axisLine={{ stroke: chartFrame.grid }} tickLine={false} />
              <YAxis width={42} tick={{ fill: chartFrame.axis }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: chartFrame.panel, border: `1px solid ${chartFrame.border}`, borderRadius: 8 }}
                labelStyle={{ color: "#e9f4ef" }}
                formatter={(value, name) => [`${Number(value).toFixed(3)} V`, name]}
              />
              <Line type="monotone" dataKey="voh" name="VOH" stroke="#67e8c3" strokeWidth={2.8} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="ripple" name="Ripple" stroke="#f5b759" strokeWidth={2.8} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Delay and overlap">
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={metrics} margin={{ top: 12, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={chartFrame.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="node" tick={{ fill: chartFrame.axis }} axisLine={{ stroke: chartFrame.grid }} tickLine={false} />
              <YAxis width={42} tick={{ fill: chartFrame.axis }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: chartFrame.panel, border: `1px solid ${chartFrame.border}`, borderRadius: 8 }}
                labelStyle={{ color: "#e9f4ef" }}
                formatter={(value, name) => {
                  if (name === "overlapRatio") return [toPercent(Number(value)), "Overlap"];
                  return [formatMicroseconds(Number(value)), "Delay"];
                }}
              />
              <Area type="monotone" dataKey="overlapRatio" name="overlapRatio" stroke="#ff6b5f" fill="rgba(255, 107, 95, 0.22)" />
              <Line type="monotone" dataKey="delayUs" name="delayUs" stroke="#80bfff" strokeWidth={2.8} dot={{ r: 3 }} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>
    </section>
  );
}

function ChartPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="chart-panel">
      <h3>{title}</h3>
      {children}
    </div>
  );
}
