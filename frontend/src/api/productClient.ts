import type {
  AnalysisRun,
  ArtifactRef,
  DesignVersion,
  EvidenceBoundary,
  EvidenceRecord,
  InputSnapshot,
  IssueRecord,
  ProductErrorPayload,
  ProductProject,
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
    listProjects: (workspaceId: string) => request<ProductProject[]>(`/api/v1/workspaces/${workspaceId}/projects`),
    createProject: (payload: { workspace_id: string; name: string; circuit_profile_id: string; spec_revision_id: string }) =>
      request<ProductProject>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) }),
    getProject: (projectId: string) => request<ProductProject>(`/api/v1/projects/${projectId}`),
    getProjectOverview: (projectId: string) => request<Record<string, unknown>>(`/api/v1/projects/${projectId}/overview`),
    getDesignVersion: (versionId: string) => request<DesignVersion>(`/api/v1/design-versions/${versionId}`),
    previewInput: (versionId: string, form: FormData) =>
      request<InputSnapshot>(`/api/v1/design-versions/${versionId}/inputs/preview`, { method: "POST", body: form }),
    createAnalysis: (versionId: string, payload: { input_manifest_ref: ArtifactRef; case_id: string }) =>
      request<AnalysisRun>(`/api/v1/design-versions/${versionId}/analysis-runs`, { method: "POST", body: JSON.stringify(payload) }),
    getAnalysis: (runId: string) => request<AnalysisRun>(`/api/v1/analysis-runs/${runId}`),
    getAnalysisBundle: (runId: string) => request<{ artifacts: string[] }>(`/api/v1/analysis-runs/${runId}/bundle`),
    getAnalysisIssues: (runId: string) => request<{ issues: IssueRecord[] }>(`/api/v1/analysis-runs/${runId}/issues`),
    getAnalysisEvidence: (runId: string) => request<{ boundary: EvidenceBoundary; records: EvidenceRecord[] }>(`/api/v1/analysis-runs/${runId}/evidence`),
  };
}

export type ProductClient = ReturnType<typeof createProductClient>;
