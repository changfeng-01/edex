import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { DesignVersionPage } from "./DesignVersionPage";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/project_1/versions/version_1"]}>
      <Routes>
        <Route path="/projects/:projectId/versions/:versionId" element={<DesignVersionPage />} />
        <Route path="/analysis/:runId" element={<h1>Analysis destination</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

it("requires waveform and params, then confirms a warned preview before analysis", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse({ design_version_id: "version_1", label: "baseline" }))
    .mockResolvedValueOnce(jsonResponse({
      input_snapshot_id: "input_1",
      preview_status: "preview_ready_with_warnings",
      preview: { warnings: ["partial node coverage"] },
      manifest_ref: { uri: "artifact://input/manifest.json", key: "input/manifest.json", size_bytes: 10, sha256: "a".repeat(64) },
    }, 201))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_1", status: "completed" }, 201));
  renderPage();
  const waveform = new File(["time,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" });
  const params = new File(["clock_period_us: 16.7\n"], "params.yaml", { type: "application/yaml" });
  fireEvent.change(screen.getByLabelText("Waveform CSV"), { target: { files: [waveform] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(screen.getByText("Parameter YAML is required.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Parameter YAML"), { target: { files: [params] } });
  expect(screen.getByText("waveform.csv selected")).toBeInTheDocument();
  expect(screen.getByText("params.yaml selected")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview warning")).toBeInTheDocument();
  expect(screen.getByText("partial node coverage")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm and run" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Analysis destination" })).toBeInTheDocument());
});

it("blocks analysis after preview failure", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse({ design_version_id: "version_1", label: "baseline" }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ error_code: "INPUT_PREVIEW_FAILED", message: "Malformed waveform", details: {}, retryable: false, artifact_refs: [] }), { status: 422, headers: { "Content-Type": "application/json" } }));
  renderPage();
  fireEvent.change(screen.getByLabelText("Waveform CSV"), { target: { files: [new File(["bad"], "bad.csv")] } });
  fireEvent.change(screen.getByLabelText("Parameter YAML"), { target: { files: [new File(["clock: bad"], "params.yaml")] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview failed")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm and run" })).not.toBeInTheDocument();
  expect(screen.getByText("bad.csv selected")).toBeInTheDocument();
  expect(screen.getByText("params.yaml selected")).toBeInTheDocument();
});

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ schema_version: "1.0", data }), { status, headers: { "Content-Type": "application/json" } });
}
