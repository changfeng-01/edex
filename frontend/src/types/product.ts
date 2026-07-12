export interface EvidenceBoundary {
  data_source: "real_simulation_csv" | string;
  engineering_validity: "simulation_only" | string;
  must_resimulate: boolean;
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

export interface DesignVersion {
  design_version_id: string;
  project_id?: string;
  label: string;
  created_at?: string;
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
