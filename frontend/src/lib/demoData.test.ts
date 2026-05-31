import { describe, expect, it, vi } from "vitest";

import { formatStatusLabel, hasAfterValue, loadProductDemoDashboard } from "./demoData";

describe("product-demo dashboard data", () => {
  it("maps evidence workflow statuses to safe display labels", () => {
    expect(formatStatusLabel("awaiting_rerun_results")).toBe("等待重跑验证");
    expect(formatStatusLabel("ready_for_rerun")).toBe("等待重跑验证");
    expect(formatStatusLabel("awaiting_candidate_generation")).toBe("等待候选生成");
    expect(formatStatusLabel("pass")).toBe("通过");
    expect(formatStatusLabel("missing")).toBe("缺失");
  });

  it("does not treat empty after values as chartable data", () => {
    expect(hasAfterValue(null)).toBe(false);
    expect(hasAfterValue(undefined)).toBe(false);
    expect(hasAfterValue("")).toBe(false);
    expect(hasAfterValue(0)).toBe(true);
  });

  it("loads partial static resources and keeps fallback data available", async () => {
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
    expect(data.resourceErrors.length).toBeGreaterThan(0);
  });
});
