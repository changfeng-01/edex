import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CircuitPilot 仪表盘", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/dashboard_summary.json")) {
        return jsonResponse({
          case_id: "public_demo",
          run_id: "public_demo_run",
          overall_status: "FAIL_OVERLAP",
          overall_score: 62,
          hard_constraint_passed: false,
          validation_status: "awaiting_rerun_results",
          candidate_status: "available",
          evidence: {
            data_source: "real_simulation_csv",
            engineering_validity: "simulation_only",
            evidence_level: "level_1_external_csv",
            simulation_backend: "external_csv",
            mock_used: false,
            pdk_available: false,
            ngspice_available: false,
            reportable_as_real_ngspice: false,
            optimizer_claim_level: "candidate_generated",
          },
        });
      }
      if (url.endsWith("/dashboard_tables.json")) {
        return jsonResponse({
          constraints: {
            rows: [
              { constraint: "Seq_pass", status: "pass", current_value: "True", threshold: "True", reason: "sequence available" },
              { constraint: "Max_overlap_ratio", status: "fail", current_value: "0.333333", threshold: "0.1", reason: "overlap exceeds limit" },
            ],
          },
          candidates: {
            rows: [
              {
                rank: 1,
                candidate_id: "cand_001",
                parameter_changes: "drive_resistance: 1000",
                trigger_metric: "Max_overlap_ratio",
                strategy: "constrained_random",
                search_score: 85,
                status: "ready_for_rerun",
                data_source: "real_simulation_csv",
                engineering_validity: "simulation_only",
              },
            ],
          },
          before_after: {
            rows: [
              {
                metric: "overall_score",
                before_value: 62,
                after_value: null,
                delta: null,
                status: "awaiting_rerun_results",
                unit: null,
              },
            ],
          },
        });
      }
      if (url.endsWith("/dashboard_figures.json")) {
        return jsonResponse({
          waveform: { file: "fig01_waveform_overview.png", title: "Waveform" },
        });
      }
      if (url.endsWith("/presentation_manifest.json")) {
        return jsonResponse({
          reports: ["executive_summary.md", "demo_report.md", "handoff_notes.md"],
        });
      }
      if (url.endsWith(".md")) {
        return textResponse("# Handoff\nStatic report preview.");
      }
      return textResponse("", 404);
    });
  });

  it("保持产品演示状态和仿真边界可见", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: /CircuitPilot 演示仪表盘/ })).toBeInTheDocument();
    expect(screen.getAllByText(/FAIL_OVERLAP/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/simulation_only/).length).toBeGreaterThan(0);
    expect(screen.getByText(/不代表物理验证、硅验证或流片验证/)).toBeInTheDocument();
    expect(screen.getAllByText("等待重跑验证").length).toBeGreaterThan(0);
  });

  it("用中文渲染交付模块且不夸大验证结论", async () => {
    render(<App />);

    expect(await screen.findByRole("region", { name: "候选参数排序" })).toBeInTheDocument();
    expect(screen.getByText(/下一轮重跑候选建议/)).toBeInTheDocument();
    expect(screen.getByText("尚未生成 after-run 结果")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "报告交付" })).toBeInTheDocument();
    expect(screen.queryByText(/validated improvement/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/silicon verified/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/physical validation achieved/i)).not.toBeInTheDocument();
  });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(payload: string, status = 200): Response {
  return new Response(payload, {
    status,
    headers: { "Content-Type": "text/plain" },
  });
}
