export interface EvidenceBoundary {
  data_source: "real_simulation_csv" | string;
  engineering_validity: "simulation_only" | string;
  must_resimulate: boolean;
}

export interface Workspace {
  workspace_id: string;
  name: string;
  created_at: string;
  schema_version?: string;
}

export interface ProjectCreatePayload {
  workspace_id: string;
  name: string;
  circuit_profile_id: string;
  spec_revision_id: string;
}

export interface ProductProject {
  project_id: string;
  workspace_id: string;
  name: string;
  circuit_profile_id: string;
  spec_revision_id: string;
  status: string;
  created_at: string;
}

export interface DesignVersionCreatePayload {
  label: string;
  parameter_set_ref?: string | null;
  netlist_ref?: string | null;
  parent_version_id?: string | null;
}

export interface DesignVersion {
  design_version_id: string;
  project_id: string;
  label: string;
  parameter_set_ref?: string | null;
  netlist_ref?: string | null;
  parent_version_id?: string | null;
  source_candidate_id?: string | null;
  created_at: string;
}

export interface ArtifactRef {
  uri: string;
  key: string;
  size_bytes: number;
  sha256: string;
}

export interface InputSnapshot {
  input_snapshot_id: string;
  design_version_id?: string;
  preview_status: "preview_ready" | "preview_ready_with_warnings" | string;
  preview: { warnings?: string[]; [key: string]: unknown };
  manifest_ref: ArtifactRef;
}

export interface AnalysisRun {
  analysis_run_id: string;
  design_version_id?: string;
  status: "queued" | "running" | "completed" | "failed" | "evidence_incomplete" | string;
  hard_constraint_passed?: boolean;
  evidence_boundary?: EvidenceBoundary;
  artifact_bundle_ref?: ArtifactRef | string | null;
  missing_evidence?: string[];
}

export interface AnalysisRunCreatePayload {
  input_manifest_ref: ArtifactRef;
  case_id: string;
  circuit_profile?: string | null;
  topology?: string | null;
  stage_count?: number | null;
  output_node_pattern?: string;
  generate_readonly_suggestions?: boolean;
  run_llm_analysis?: boolean;
}

export interface IssueRecord {
  issue_id: string;
  constraint_key: string;
  category: string;
  severity: string;
  affected_nodes?: string[];
  metric_refs?: string[];
  possible_causes?: string[];
  recommended_actions?: string[];
  evidence_refs?: string[];
  classification: string;
}

export interface EvidenceRecord {
  evidence_id: string;
  evidence_type: string;
  source_ref: string;
  checksum?: string;
}

export interface ProductErrorPayload {
  error_code: string;
  message: string;
  details: Record<string, unknown>;
  retryable: boolean;
  artifact_refs: string[];
}

export interface OptimizationExperiment {
  experiment_id: string;
  project_id: string;
  baseline_design_version_id: string;
  strategy_config: Record<string, unknown>;
  state: string;
  created_at: string;
}

export interface OptimizationCandidate {
  candidate_id: string;
  experiment_id: string;
  parent_design_version_id: string;
  parameter_changes: Record<string, unknown>;
  strategy: string;
  reason_codes: string[];
  selection_scores?: Record<string, unknown>;
  selection_score?: number | null;
  evaluated_score?: number | null;
  status: string;
  must_resimulate: boolean;
  simulation_job_id?: string | null;
  result_design_version_id?: string | null;
}

export interface SimulationJob {
  simulation_job_id: string;
  project_id?: string | null;
  candidate_ids: string[];
  adapter_type: string;
  status: string;
  export_attempt?: number;
  import_attempt?: number;
  batch_ref?: ArtifactRef | string | null;
  result_ref?: ArtifactRef | string | null;
  error_code?: string | null;
  retryable?: boolean;
}

export interface SimulationImportPreview {
  simulation_job_id: string;
  manifest_sha256: string;
  result_sha256: string;
  row_count: number;
  warnings: Array<{ type: string; [key: string]: unknown }>;
}

export interface EvaluatedComparison {
  comparison_id: string;
  project_id: string;
  baseline_design_version_id: string;
  result_design_version_id: string;
  baseline_analysis_run_id?: string;
  result_analysis_run_id?: string;
  metric_deltas: Record<string, unknown>;
  constraint_changes: Record<string, unknown>;
  evidence_ids: string[];
  verdict: "improved" | "regressed" | "neutral" | "evidence_insufficient" | string;
  created_at: string;
}
