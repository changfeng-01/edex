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

export type ScalarValue = string | number | boolean | null | undefined;

export interface EvidenceBoundary {
  data_source?: string;
  engineering_validity?: string;
  evidence_level?: string;
  simulation_backend?: string;
  mock_used?: boolean | string;
  pdk_available?: boolean | string;
  ngspice_available?: boolean | string;
  reportable_as_real_ngspice?: boolean | string;
  optimizer_claim_level?: string;
}

export interface DashboardSummary {
  case_id: string;
  run_id?: string;
  overall_status?: string;
  overall_score?: number | string | null;
  hard_constraint_passed?: boolean | string | null;
  validation_status?: string;
  candidate_status?: string;
  evidence?: EvidenceBoundary;
}

export interface DashboardTable<T> {
  file?: string;
  rows?: T[];
}

export interface ConstraintRow {
  constraint: string;
  status: "pass" | "fail" | "unknown" | "missing" | string;
  current_value?: string | number | null;
  threshold?: string | number | null;
  reason?: string;
}

export interface CandidateRow {
  rank?: number | string;
  candidate_id?: string;
  priority?: string | number;
  parameter_changes?: string;
  trigger_metric?: string;
  strategy?: string;
  search_score?: string | number;
  status?: string;
  data_source?: string;
  engineering_validity?: string;
}

export interface BeforeAfterRow {
  metric: string;
  before_value?: string | number | null;
  after_value?: string | number | null;
  delta?: string | number | null;
  status?: string;
  unit?: string | null;
}

export interface DashboardTables {
  run_summary?: DashboardTable<Record<string, ScalarValue>>;
  constraints?: DashboardTable<ConstraintRow>;
  candidates?: DashboardTable<CandidateRow>;
  before_after?: DashboardTable<BeforeAfterRow>;
}

export interface DashboardFigure {
  key: string;
  file: string;
  title: string;
  size_bytes?: number;
  source_manifest_available?: boolean;
  url: string;
}

export interface DashboardFiguresPayload {
  [key: string]: {
    file?: string;
    title?: string;
    size_bytes?: number;
    source_manifest_available?: boolean;
  };
}

export interface PresentationManifest {
  case_id?: string;
  package_version?: string;
  input_dir?: string;
  validation_status?: string;
  candidate_status?: string;
  evidence?: EvidenceBoundary;
  tables?: Record<string, string>;
  figures?: Record<string, string>;
  reports?: string[];
}

export interface ReportPreview {
  file: string;
  title: string;
  url: string;
  content: string | null;
  error?: string;
}

export interface ProductDemoDashboardData {
  caseId: string;
  basePath: string;
  summary: DashboardSummary;
  tables: DashboardTables;
  figures: DashboardFigure[];
  manifest: PresentationManifest | null;
  reports: ReportPreview[];
  resourceErrors: string[];
}
