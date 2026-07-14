import type {
  AnalysisRun,
  AnalysisRunCreatePayload,
  ArtifactRef,
  DesignVersion,
  DesignVersionCreatePayload,
  EvidenceBoundary,
  EvidenceRecord,
  EvaluatedComparison,
  InputSnapshot,
  IssueRecord,
  OptimizationCandidate,
  OptimizationExperiment,
  ProductErrorPayload,
  ProjectCreatePayload,
  ProductProject,
  SimulationImportPreview,
  SimulationJob,
  Workspace,
} from "../types/product";

const configuredBaseUrl = String(import.meta.env.VITE_PRODUCT_API_BASE_URL || import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ProductApiError extends Error {
  readonly errorCode: string;
  readonly details: Record<string, unknown>;
  readonly retryable: boolean;
  readonly artifactRefs: string[];
  readonly status: number;

  constructor(payload: ProductErrorPayload, status: number) {
    super(payload.message);
    this.name = "ProductApiError";
    this.errorCode = payload.error_code;
    this.details = payload.details;
    this.retryable = payload.retryable;
    this.artifactRefs = payload.artifact_refs;
    this.status = status;
  }
}

export function createProductClient(baseUrl = configuredBaseUrl) {
  const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
    const headers = new Headers(init.headers);
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
    const payload = await response.json();
    if (!response.ok) throw new ProductApiError(payload as ProductErrorPayload, response.status);
    return (payload as { schema_version: string; data: T }).data;
  };

  return {
    listWorkspaces: () => request<Workspace[]>("/api/v1/workspaces"),
    createWorkspace: (name: string) =>
      request<Workspace>("/api/v1/workspaces", { method: "POST", body: JSON.stringify({ name }) }),
    listProjects: (workspaceId: string) => request<ProductProject[]>(`/api/v1/workspaces/${workspaceId}/projects`),
    createProject: (payload: ProjectCreatePayload) =>
      request<ProductProject>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) }),
    getProject: (projectId: string) => request<ProductProject>(`/api/v1/projects/${projectId}`),
    getProjectOverview: (projectId: string) => request<Record<string, unknown>>(`/api/v1/projects/${projectId}/overview`),
    createDesignVersion: (projectId: string, payload: DesignVersionCreatePayload) =>
      request<DesignVersion>(`/api/v1/projects/${projectId}/design-versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getDesignVersion: (versionId: string) => request<DesignVersion>(`/api/v1/design-versions/${versionId}`),
    previewInput: (versionId: string, form: FormData) =>
      request<InputSnapshot>(`/api/v1/design-versions/${versionId}/inputs/preview`, { method: "POST", body: form }),
    createAnalysis: (versionId: string, payload: AnalysisRunCreatePayload) =>
      request<AnalysisRun>(`/api/v1/design-versions/${versionId}/analysis-runs`, { method: "POST", body: JSON.stringify(payload) }),
    getAnalysis: (runId: string) => request<AnalysisRun>(`/api/v1/analysis-runs/${runId}`),
    getAnalysisBundle: (runId: string) => request<{ artifacts: string[] }>(`/api/v1/analysis-runs/${runId}/bundle`),
    getAnalysisIssues: (runId: string) => request<{ issues: IssueRecord[] }>(`/api/v1/analysis-runs/${runId}/issues`),
    getAnalysisEvidence: (runId: string) => request<{ boundary: EvidenceBoundary; records: EvidenceRecord[] }>(`/api/v1/analysis-runs/${runId}/evidence`),
    getExperiment: (experimentId: string) => request<OptimizationExperiment>(`/api/v1/experiments/${experimentId}`),
    createExperiment: (projectId: string, baselineDesignVersionId: string, strategyConfig: Record<string, unknown>) =>
      request<OptimizationExperiment>(`/api/v1/projects/${projectId}/experiments`, {
        method: "POST",
        body: JSON.stringify({ baseline_design_version_id: baselineDesignVersionId, strategy_config: strategyConfig }),
      }),
    listCandidates: (experimentId: string) => request<OptimizationCandidate[]>(`/api/v1/experiments/${experimentId}/candidates`),
    generateCandidates: (experimentId: string, strategy: string, maxCandidates: number, seed: number) =>
      request<OptimizationCandidate[]>(`/api/v1/experiments/${experimentId}/candidates:generate`, {
        method: "POST",
        body: JSON.stringify({ strategy, max_candidates: maxCandidates, seed }),
      }),
    approveCandidate: (candidateId: string, actorId = "operator") =>
      request<OptimizationCandidate>(`/api/v1/candidates/${candidateId}:approve`, {
        method: "POST",
        body: JSON.stringify({ actor_id: actorId }),
      }),
    rejectCandidate: (candidateId: string, reason: string, actorId = "operator") =>
      request<OptimizationCandidate>(`/api/v1/candidates/${candidateId}:reject`, {
        method: "POST",
        body: JSON.stringify({ actor_id: actorId, reason }),
      }),
    getSimulationJob: (jobId: string) => request<SimulationJob>(`/api/v1/simulation-jobs/${jobId}`),
    createSimulationJob: (candidateIds: string[]) => request<SimulationJob>("/api/v1/simulation-jobs", {
      method: "POST",
      body: JSON.stringify({ candidate_ids: candidateIds, adapter_type: "manual" }),
    }),
    exportSimulationJob: (jobId: string) => request<SimulationJob>(`/api/v1/simulation-jobs/${jobId}:export`, { method: "POST" }),
    previewSimulationImport: (jobId: string, file: File) => {
      const form = new FormData();
      form.append("results", file);
      return request<SimulationImportPreview>(`/api/v1/simulation-jobs/${jobId}/imports:preview`, { method: "POST", body: form });
    },
    commitSimulationImport: (jobId: string, manifestSha256: string) =>
      request<SimulationJob>(`/api/v1/simulation-jobs/${jobId}/imports:commit`, {
        method: "POST",
        body: JSON.stringify({ manifest_sha256: manifestSha256 }),
      }),
    retrySimulationJob: (jobId: string) => request<SimulationJob>(`/api/v1/simulation-jobs/${jobId}:retry`, { method: "POST" }),
    getComparison: (comparisonId: string) => request<EvaluatedComparison>(`/api/v1/comparisons/${comparisonId}`),
    createComparison: (payload: {
      project_id: string;
      baseline_design_version_id: string;
      result_design_version_id: string;
      baseline_analysis_run_id: string;
      result_analysis_run_id: string;
    }) => request<EvaluatedComparison>("/api/v1/comparisons", { method: "POST", body: JSON.stringify(payload) }),
    confirmCandidate: (candidateId: string, comparisonId: string) => request<OptimizationCandidate>(`/api/v1/candidates/${candidateId}:confirm?comparison_id=${encodeURIComponent(comparisonId)}`, { method: "POST" }),
  };
}

export type ProductClient = ReturnType<typeof createProductClient>;
