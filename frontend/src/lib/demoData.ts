import type {
  DashboardFigure,
  DashboardFiguresPayload,
  DashboardSummary,
  DashboardTables,
  PresentationManifest,
  ProductDemoDashboardData,
  ReportPreview,
} from "../types";

export const DEFAULT_CASE_ID = "public_demo";

const EXPECTED_FIGURES = [
  { key: "waveform", file: "fig01_waveform_overview.png", title: "波形总览" },
  { key: "constraints", file: "fig02_constraint_status.png", title: "约束状态" },
  { key: "metrics", file: "fig03_metric_comparison.png", title: "指标对比" },
  { key: "candidates", file: "fig04_candidate_ranking.png", title: "候选参数排序" },
  { key: "before_after", file: "fig05_before_after_comparison.png", title: "重跑前后对比" },
  { key: "evidence", file: "fig06_evidence_card.png", title: "证据边界卡片" },
] as const;

const EXPECTED_REPORTS = [
  { file: "executive_summary.md", title: "执行摘要" },
  { file: "demo_report.md", title: "演示报告" },
  { file: "handoff_notes.md", title: "交付说明" },
] as const;

interface ApiDashboardBundle {
  case_id?: string;
  summary?: DashboardSummary;
  tables?: DashboardTables;
  figures?: Array<{
    key?: string;
    title?: string;
    file?: string;
    url?: string;
    exists?: boolean;
    size_bytes?: number;
    source_manifest_available?: boolean;
  }>;
  reports?: Array<{
    name?: string;
    file?: string;
    title?: string;
    url?: string;
    exists?: boolean;
    content?: string | null;
    error?: string;
  }>;
  manifest?: PresentationManifest;
}

export function getCaseIdFromLocation(locationSearch = window.location.search): string {
  const params = new URLSearchParams(locationSearch);
  const caseId = params.get("case_id")?.trim();
  return caseId || DEFAULT_CASE_ID;
}

export async function loadProductDemoDashboard(caseId = getCaseIdFromLocation()): Promise<ProductDemoDashboardData> {
  const encodedCaseId = encodeURIComponent(caseId);
  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    return loadProductDemoDashboardFromApi(apiBaseUrl, encodedCaseId, caseId);
  }
  const basePath = `/demo_data/${encodedCaseId}`;
  const errors: string[] = [];

  const [summaryResult, tablesResult, figuresResult, manifestResult] = await Promise.all([
    fetchJson<DashboardSummary>(`${basePath}/dashboard_summary.json`),
    fetchJson<DashboardTables>(`${basePath}/dashboard_tables.json`),
    fetchJson<DashboardFiguresPayload>(`${basePath}/dashboard_figures.json`),
    fetchJson<PresentationManifest>(`${basePath}/presentation_manifest.json`),
  ]);

  for (const result of [summaryResult, tablesResult, figuresResult, manifestResult]) {
    if (result.error) {
      errors.push(result.error);
    }
  }

  const summary = summaryResult.data ?? fallbackSummary(caseId);
  const tables = tablesResult.data ?? {};
  const figuresPayload = figuresResult.data ?? {};
  const manifest = manifestResult.data ?? null;
  const reports = await loadReportPreviews(basePath, manifest);

  for (const report of reports) {
    if (report.error) {
      errors.push(report.error);
    }
  }

  return {
    caseId,
    basePath,
    summary,
    tables,
    figures: buildFigures(basePath, figuresPayload, manifest),
    manifest,
    reports,
    resourceErrors: errors,
  };
}

async function loadProductDemoDashboardFromApi(
  apiBaseUrl: string,
  encodedCaseId: string,
  caseId: string,
): Promise<ProductDemoDashboardData> {
  const url = `${apiBaseUrl}/api/cases/${encodedCaseId}/bundle`;
  const result = await fetchJson<ApiDashboardBundle>(url);
  if (result.data) {
    return normalizeApiBundle(result.data, apiBaseUrl, encodedCaseId, caseId);
  }
  return {
    caseId,
    basePath: `${apiBaseUrl}/api/cases/${encodedCaseId}`,
    summary: fallbackSummary(caseId),
    tables: {},
    figures: [],
    manifest: null,
    reports: [],
    resourceErrors: result.error ? [result.error] : [`${url} 加载失败`],
  };
}

async function normalizeApiBundle(
  bundle: ApiDashboardBundle,
  apiBaseUrl: string,
  encodedCaseId: string,
  fallbackCaseId: string,
): Promise<ProductDemoDashboardData> {
  const caseId = bundle.case_id ?? bundle.summary?.case_id ?? fallbackCaseId;
  const basePath = `${apiBaseUrl}/api/cases/${encodedCaseId}`;
  const summary = bundle.summary ?? fallbackSummary(caseId);
  const reports = await normalizeApiReports(bundle.reports ?? [], apiBaseUrl);
  const resourceErrors = reports.flatMap((report) => (report.error ? [report.error] : []));
  return {
    caseId,
    basePath,
    summary,
    tables: bundle.tables ?? {},
    figures: normalizeApiFigures(bundle.figures ?? [], apiBaseUrl),
    manifest: bundle.manifest ?? null,
    reports,
    resourceErrors,
  };
}

function normalizeApiFigures(figures: ApiDashboardBundle["figures"], apiBaseUrl: string): DashboardFigure[] {
  return (figures ?? []).map((figure) => {
    const expected = EXPECTED_FIGURES.find((item) => item.key === figure.key);
    const file = figure.file ?? expected?.file ?? "";
    return {
      key: figure.key ?? file,
      file,
      title: expected?.title ?? figure.title ?? file,
      size_bytes: figure.size_bytes,
      source_manifest_available: figure.source_manifest_available,
      url: resolveApiUrl(apiBaseUrl, figure.url ?? ""),
    };
  });
}

async function normalizeApiReports(reports: ApiDashboardBundle["reports"], apiBaseUrl: string): Promise<ReportPreview[]> {
  return Promise.all(
    (reports ?? []).map(async (report) => {
      const file = report.file ?? report.name ?? "";
      const known = EXPECTED_REPORTS.find((item) => item.file === file);
      const url = resolveApiUrl(apiBaseUrl, report.url ?? "");
      const result = report.content === undefined && url ? await fetchText(url) : { data: report.content ?? null, error: report.error };
      return {
        file,
        title: known?.title ?? report.title ?? titleFromFile(file),
        url,
        content: result.data ?? null,
        error: result.error,
      };
    }),
  );
}

function resolveApiUrl(apiBaseUrl: string, url: string): string {
  if (!url) {
    return "";
  }
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  return `${apiBaseUrl}${url.startsWith("/") ? url : `/${url}`}`;
}

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
}

export function fallbackSummary(caseId: string): DashboardSummary {
  return {
    case_id: caseId,
    run_id: "not_available",
    overall_status: "missing_dashboard_summary",
    overall_score: null,
    hard_constraint_passed: null,
    validation_status: "unknown",
    candidate_status: "unknown",
    evidence: {
      data_source: "not_available",
      engineering_validity: "simulation_only",
      evidence_level: "not_available",
      simulation_backend: "not_available",
      mock_used: "unknown",
      optimizer_claim_level: "not_available",
    },
  };
}

export function formatStatusLabel(status: string | undefined | null): string {
  switch ((status ?? "").trim()) {
    case "awaiting_rerun_results":
    case "ready_for_rerun":
      return "等待重跑验证";
    case "awaiting_candidate_generation":
      return "候选待生成";
    case "available":
      return "可展示";
    case "pass":
      return "通过";
    case "fail":
      return "失败";
    case "unknown":
      return "未知";
    case "missing":
      return "缺失";
    case "":
      return "未提供";
    default:
      return status ?? "未提供";
  }
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  return String(value);
}

export function hasAfterValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

export function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function buildFigures(
  basePath: string,
  figuresPayload: DashboardFiguresPayload,
  manifest: PresentationManifest | null,
): DashboardFigure[] {
  return EXPECTED_FIGURES.map((expected) => {
    const payload = figuresPayload[expected.key] ?? {};
    const file = payload.file ?? manifest?.figures?.[expected.key] ?? expected.file;
    return {
      key: expected.key,
      file,
      title: expected.title,
      size_bytes: payload.size_bytes,
      source_manifest_available: payload.source_manifest_available,
      url: `${basePath}/figures/${file}`,
    };
  });
}

async function loadReportPreviews(basePath: string, manifest: PresentationManifest | null): Promise<ReportPreview[]> {
  const files = manifest?.reports?.length ? manifest.reports : EXPECTED_REPORTS.map((report) => report.file);
  return Promise.all(
    files.map(async (file) => {
      const known = EXPECTED_REPORTS.find((report) => report.file === file);
      const url = `${basePath}/reports/${file}`;
      const result = await fetchText(url);
      return {
        file,
        title: known?.title ?? titleFromFile(file),
        url,
        content: result.data ?? null,
        error: result.error,
      };
    }),
  );
}

function titleFromFile(file: string): string {
  return file.replace(/\.md$/i, "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function fetchJson<T>(url: string): Promise<{ data: T | null; error?: string }> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return { data: null, error: `${url} 返回 ${response.status}` };
    }
    return { data: (await response.json()) as T };
  } catch (error) {
    return { data: null, error: `${url} 加载失败：${String(error)}` };
  }
}

async function fetchText(url: string): Promise<{ data: string | null; error?: string }> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return { data: null, error: `${url} 返回 ${response.status}` };
    }
    return { data: await response.text() };
  } catch (error) {
    return { data: null, error: `${url} 加载失败：${String(error)}` };
  }
}
