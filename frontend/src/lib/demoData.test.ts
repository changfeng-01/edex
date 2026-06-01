import { afterEach, describe, expect, it, vi } from "vitest";

import { formatStatusLabel, hasAfterValue, loadProductDemoDashboard } from "./demoData";

describe("product-demo 仪表盘数据", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("将证据工作流状态映射为中文显示标签", () => {
    expect(formatStatusLabel("awaiting_rerun_results")).toBe("等待重跑验证");
    expect(formatStatusLabel("ready_for_rerun")).toBe("等待重跑验证");
    expect(formatStatusLabel("awaiting_candidate_generation")).toBe("候选待生成");
    expect(formatStatusLabel("pass")).toBe("通过");
    expect(formatStatusLabel("missing")).toBe("缺失");
  });

  it("不会把空 after 值当作可绘图数据", () => {
    expect(hasAfterValue(null)).toBe(false);
    expect(hasAfterValue(undefined)).toBe(false);
    expect(hasAfterValue("")).toBe(false);
    expect(hasAfterValue(0)).toBe(true);
  });

  it("加载部分静态资源时保留兜底数据", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/dashboard_summary.json")) {
        return new Response(
          JSON.stringify({
            case_id: "partial_demo",
            validation_status: "awaiting_rerun_results",
            evidence: { data_source: "real_simulation_csv", engineering_validity: "simulation_only" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("", { status: 404 });
    });

    const data = await loadProductDemoDashboard("partial_demo");

    expect(data.summary.case_id).toBe("partial_demo");
    expect(data.summary.evidence?.engineering_validity).toBe("simulation_only");
    expect(data.tables.constraints?.rows ?? []).toEqual([]);
    expect(data.figures).toHaveLength(6);
    expect(data.figures[0].title).toBe("波形总览");
    expect(data.resourceErrors.length).toBeGreaterThan(0);
  });

  it("配置 VITE_API_BASE_URL 时加载后端 bundle", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "https://api.example.test/api/cases/api_demo/bundle") {
        return new Response(
          JSON.stringify({
            caseId: "api_demo",
            basePath: "/api/cases/api_demo",
            summary: {
              case_id: "api_demo",
              evidence: { data_source: "real_simulation_csv", engineering_validity: "simulation_only" },
            },
            tables: { constraints: { rows: [{ constraint: "Seq_pass", status: "fail" }] } },
            figures: [],
            manifest: { case_id: "api_demo" },
            reports: [],
            resourceErrors: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("", { status: 404 });
    });

    const data = await loadProductDemoDashboard("api_demo");

    expect(fetchMock).toHaveBeenCalledWith("https://api.example.test/api/cases/api_demo/bundle");
    expect(data.basePath).toBe("https://api.example.test/api/cases/api_demo");
    expect(data.summary.evidence?.engineering_validity).toBe("simulation_only");
    expect(data.tables.constraints?.rows?.[0]?.constraint).toBe("Seq_pass");
  });
});
