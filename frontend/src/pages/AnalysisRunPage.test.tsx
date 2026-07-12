import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AnalysisRunPage } from "./AnalysisRunPage";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderRun(run: Record<string, unknown>, resourceFailure = false) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/issues")) return resourceFailure ? errorResponse("ARTIFACT_NOT_FOUND") : jsonResponse({ issues: [{ issue_id: "issue_1", constraint_key: "FAIL_RIPPLE", category: "waveform_quality", severity: "high", classification: "known", evidence_refs: ["artifact://diagnosis.md"] }] });
    if (url.endsWith("/evidence")) return jsonResponse({ boundary: { data_source: "real_simulation_csv", engineering_validity: "simulation_only", must_resimulate: true }, records: [{ evidence_id: "evidence_1", evidence_type: "real_summary.json", source_ref: "artifact://run/real_summary.json" }] });
    if (url.endsWith("/bundle")) return jsonResponse({ artifacts: ["artifact://run/next_candidates.csv", "artifact://run/report.md"] });
    return jsonResponse(run);
  });
  return render(<MemoryRouter initialEntries={["/analysis/run_1"]}><Routes><Route path="/analysis/:runId" element={<AnalysisRunPage />} /></Routes></MemoryRouter>);
}

it.each([
  ["running", "Analysis running"],
  ["completed", "Analysis completed"],
  ["evidence_incomplete", "Evidence incomplete"],
])("renders %s as a distinct analysis state", async (status, label) => {
  renderRun({ analysis_run_id: "run_1", status, evidence_boundary: { data_source: "real_simulation_csv", engineering_validity: "simulation_only", must_resimulate: true } });
  expect(await screen.findByText(label)).toBeInTheDocument();
});

it("keeps hard-constraint failure, issues, evidence, and readonly candidates explicit", async () => {
  renderRun({ analysis_run_id: "run_1", status: "completed", hard_constraint_passed: false });
  expect(await screen.findByText("Hard constraint failed")).toBeInTheDocument();
  expect(screen.getByText("FAIL_RIPPLE")).toBeInTheDocument();
  expect(screen.getByText("data_source = real_simulation_csv")).toBeInTheDocument();
  expect(screen.getByText("engineering_validity = simulation_only")).toBeInTheDocument();
  expect(screen.getByText("must_resimulate = true")).toBeInTheDocument();
  expect(screen.getByText("Read-only suggestion · must_resimulate = true")).toBeInTheDocument();
  expect(screen.queryByText(/confirmed improvement/i)).not.toBeInTheDocument();
});

it("keeps the analysis page usable when one resource fails", async () => {
  renderRun({ analysis_run_id: "run_1", status: "completed" }, true);
  expect(await screen.findByText("ARTIFACT_NOT_FOUND")).toBeInTheDocument();
  expect(screen.getByText("Analysis completed")).toBeInTheDocument();
});

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ schema_version: "1.0", data }), { status: 200, headers: { "Content-Type": "application/json" } });
}

function errorResponse(errorCode: string): Response {
  return new Response(JSON.stringify({ error_code: errorCode, message: "Resource unavailable", details: {}, retryable: false, artifact_refs: [] }), { status: 404, headers: { "Content-Type": "application/json" } });
}
