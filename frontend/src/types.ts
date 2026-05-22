export interface RealSummary {
  run_id: string;
  run_timestamp: string;
  data_source: string;
  engineering_validity: string;
  Overall_status: string;
  stage_count: number;
  VOH_min: number;
  Delay_mean: number;
  Width_mean: number;
  Max_ripple: number;
  Max_voltage_loss: number;
  Max_overlap_ratio: number;
  Seq_pass: boolean;
  All_pulses_exist: boolean;
  FalseTriggerCount: number;
  LowFreqStable: string;
  worst_stage: number | null;
  first_failed_stage: number | null;
  notes?: string[];
}

export interface ScoreSummary {
  hard_constraint_passed: boolean;
  hard_constraint_failures: string[];
  hard_constraints: Record<
    string,
    {
      passed: boolean;
      current_value: boolean | number | string | null;
      threshold: boolean | number | string | null;
      reason: string;
    }
  >;
  warning_reasons: string[];
  function_score: number;
  quality_score: number;
  stability_score: number;
  consistency_score: number;
  cost_score: number;
  overall_score: number;
}

export interface MetricRow {
  stage: number;
  node: string;
  voh: number | null;
  delayUs: number | null;
  ripple: number | null;
  overlapRatio: number | null;
}

export interface OptimizationRow {
  runId: string;
  status: string;
  score: number | null;
  maxOverlapRatio: number | null;
  maxRipple: number | null;
  maxVoltageLoss: number | null;
  dataSource: string;
  engineeringValidity: string;
}

export interface DashboardData {
  summary: RealSummary;
  score: ScoreSummary;
  metrics: MetricRow[];
  optimization: OptimizationRow[];
}
