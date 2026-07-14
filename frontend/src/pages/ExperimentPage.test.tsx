import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { ExperimentPage } from "./ExperimentPage";


afterEach(() => vi.restoreAllMocks());

it("shows explicit approval controls and the resimulation boundary", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith(":approve")) {
      return new Response(JSON.stringify({ schema_version: "1.0", data: candidate("approved") }), { status: 200 });
    }
    if (url.endsWith("/candidates")) {
      return new Response(JSON.stringify({ schema_version: "1.0", data: [candidate("proposed")] }), { status: 200 });
    }
    return new Response(JSON.stringify({ schema_version: "1.0", data: experiment }), { status: 200 });
  });
  render(
    <MemoryRouter initialEntries={["/experiments/experiment_1"]}>
      <Routes><Route path="/experiments/:experimentId" element={<ExperimentPage />} /></Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: "Optimization experiment" })).toBeInTheDocument();
  expect(screen.getByText("must_resimulate = true")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve candidate" }));
  await waitFor(() => expect(screen.getByText("approved")).toBeInTheDocument());
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("candidate_1:approve"), expect.objectContaining({ method: "POST" }));
});

const experiment = {
  experiment_id: "experiment_1",
  project_id: "project_1",
  baseline_design_version_id: "version_1",
  strategy_config: { strategy: "rule" },
  state: "ready",
  created_at: "2026-07-12T00:00:00Z",
};
const candidate = (status: string) => ({
  candidate_id: "candidate_1",
  experiment_id: "experiment_1",
  parent_design_version_id: "version_1",
  parameter_changes: { width: 12.5 },
  strategy: "rule",
  reason_codes: ["reduce_ripple"],
  selection_score: 0.9,
  evaluated_score: null,
  status,
  must_resimulate: true,
});
