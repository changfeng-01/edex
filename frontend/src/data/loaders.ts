import { csvParse } from "d3-dsv";

import type { DashboardData, MetricRow, OptimizationRow, RealSummary, ScoreSummary } from "../types";

export const DEFAULT_SUMMARY: RealSummary = {
  run_id: "real_20260516_161123",
  run_timestamp: "2026-05-16T16:11:23",
  data_source: "real_simulation_csv",
  engineering_validity: "simulation_only",
  Overall_status: "FAIL_OVERLAP",
  stage_count: 3,
  VOH_min: 6.15,
  Delay_mean: 0.000002,
  Width_mean: 0.000003,
  Max_ripple: 0.2,
  Max_voltage_loss: 0.10000000000000053,
  Max_overlap_ratio: 0.33333333333333354,
  Seq_pass: true,
  All_pulses_exist: true,
  FalseTriggerCount: 0,
  LowFreqStable: "not_evaluable_with_current_waveform",
  worst_stage: 2,
  first_failed_stage: 1,
  notes: ["Fallback snapshot used when public data is unavailable."],
};

export const DEFAULT_SCORE: ScoreSummary = {
  hard_constraint_passed: false,
  hard_constraint_failures: ["Max_overlap_ratio exceeds max_overlap_ratio"],
  hard_constraints: {
    All_pulses_exist: { passed: true, current_value: true, threshold: true, reason: "All pulses exist" },
    Seq_pass: { passed: true, current_value: true, threshold: true, reason: "Scan sequence passed" },
    FalseTriggerCount: { passed: true, current_value: 0, threshold: 0, reason: "FalseTriggerCount is 0" },
    Max_overlap_ratio: {
      passed: false,
      current_value: 0.33333333333333354,
      threshold: 0.1,
      reason: "Max_overlap_ratio exceeds max_overlap_ratio",
    },
  },
  warning_reasons: ["LowFreqStable is not evaluable with current waveform duration", "DeviceCount is not available"],
  function_score: 80,
  quality_score: 0,
  stability_score: 60,
  consistency_score: 100,
  cost_score: 100,
  overall_score: 62,
};

const DEFAULT_METRICS_CSV = [
  "stage,node,VOH_mean,Delay,Ripple,OverlapRatio",
  "1,o1,6.15,,0.1,0.3333333333333335",
  "2,o2,6.15,0.000002,0.2,0.3333333333333332",
  "3,o3,6.15,0.000002,0,",
].join("\n");

const DEFAULT_OPTIMIZATION_CSV = [
  "run_id,Overall_status,overall_score,Max_overlap_ratio,Max_ripple,Max_voltage_loss,data_source,engineering_validity",
  "real_20260516_161123,FAIL_OVERLAP,62,0.3333333333333335,0.2,0.1000000000000005,real_simulation_csv,simulation_only",
].join("\n");

export function parseMetricRows(csvText: string): MetricRow[] {
  return csvParse(csvText).map((row) => ({
    stage: numberCell(row.stage) ?? 0,
    node: row.node ?? "",
    voh: numberCell(row.VOH_mean),
    delayUs: secondsToMicroseconds(numberCell(row.Delay)),
    ripple: numberCell(row.Ripple),
    overlapRatio: numberCell(row.OverlapRatio),
  }));
}

export function parseOptimizationRows(csvText: string): OptimizationRow[] {
  return csvParse(csvText).map((row) => ({
    runId: row.run_id ?? "",
    status: row.Overall_status || row.overall_status || "",
    score: numberCell(row.overall_score),
    maxOverlapRatio: numberCell(row.Max_overlap_ratio),
    maxRipple: numberCell(row.Max_ripple),
    maxVoltageLoss: numberCell(row.Max_voltage_loss),
    dataSource: row.data_source ?? "",
    engineeringValidity: row.engineering_validity ?? "",
  }));
}

export async function loadDashboardData(): Promise<DashboardData> {
  try {
    const [summary, score, metricsCsv, optimizationCsv] = await Promise.all([
      fetchJson<RealSummary>("/data/real_summary.json"),
      fetchJson<ScoreSummary>("/data/score_summary.json"),
      fetchText("/data/real_metrics.csv"),
      fetchText("/data/optimization_dataset.csv"),
    ]);
    return {
      summary,
      score,
      metrics: parseMetricRows(metricsCsv),
      optimization: parseOptimizationRows(optimizationCsv),
    };
  } catch {
    return fallbackData();
  }
}

export function fallbackData(): DashboardData {
  return {
    summary: DEFAULT_SUMMARY,
    score: DEFAULT_SCORE,
    metrics: parseMetricRows(DEFAULT_METRICS_CSV),
    optimization: parseOptimizationRows(DEFAULT_OPTIMIZATION_CSV),
  };
}

export function toMicroseconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${(value * 1_000_000).toFixed(2)} us`;
}

export function toSecondsAsMicroseconds(value: number | null | undefined): string {
  return toMicroseconds(value);
}

export function formatMicroseconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value.toFixed(2)} us`;
}

export function toPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function toFixedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return value.toFixed(digits);
}

function numberCell(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function secondsToMicroseconds(value: number | null): number | null {
  return value === null ? null : value * 1_000_000;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}`);
  }
  return response.json() as Promise<T>;
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}`);
  }
  return response.text();
}
