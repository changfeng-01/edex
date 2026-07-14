import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { ComparisonPage } from "./ComparisonPage";


afterEach(() => vi.restoreAllMocks());

it("renders evidence-insufficient without claiming improvement", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ schema_version: "1.0", data: {
      comparison_id: "comparison_1",
      project_id: "project_1",
      baseline_design_version_id: "version_1",
      result_design_version_id: "version_2",
      metric_deltas: {},
      constraint_changes: {},
      evidence_ids: [],
      verdict: "evidence_insufficient",
      created_at: "2026-07-12T00:00:00Z",
    } }), { status: 200 }),
  );
  render(
    <MemoryRouter initialEntries={["/comparisons/comparison_1"]}>
      <Routes><Route path="/comparisons/:comparisonId" element={<ComparisonPage />} /></Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { name: "Evaluated comparison" })).toBeInTheDocument();
  expect(screen.getByText("Evidence insufficient")).toBeInTheDocument();
  expect(screen.queryByText("Confirmed improvement")).not.toBeInTheDocument();
});
