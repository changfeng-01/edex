import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { SimulationJobPage } from "./SimulationJobPage";


afterEach(() => vi.restoreAllMocks());

it("retains the selected result file and shows preview warnings", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const data = url.endsWith("imports:preview")
      ? { simulation_job_id: "job_1", manifest_sha256: "a".repeat(64), result_sha256: "b".repeat(64), row_count: 1, warnings: [{ type: "extra_columns_preserved" }] }
      : { simulation_job_id: "job_1", candidate_ids: ["candidate_1"], adapter_type: "manual", status: "waiting_for_results", import_attempt: 0 };
    return new Response(JSON.stringify({ schema_version: "1.0", data }), { status: 200 });
  });
  render(
    <MemoryRouter initialEntries={["/simulation-jobs/job_1"]}>
      <Routes><Route path="/simulation-jobs/:jobId" element={<SimulationJobPage />} /></Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { name: "Manual simulation job" })).toBeInTheDocument();
  const file = new File(["candidate_id,overall_score"], "very-long-result-file-name.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("Simulation result CSV"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview import" }));
  expect(await screen.findByText("extra_columns_preserved")).toBeInTheDocument();
  expect(screen.getByText("very-long-result-file-name.csv")).toBeInTheDocument();
});
