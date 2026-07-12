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
      <Routes><Route path="/projects/:projectId/versions/:versionId" element={<DesignVersionPage />} /></Routes>
    </MemoryRouter>,
  );
}

it("distinguishes selected files, preview warning, and analysis submission", async () => {
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
  const file = new File(["time,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("Waveform CSV"), { target: { files: [file] } });
  expect(screen.getByText("waveform.csv selected")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview warning")).toBeInTheDocument();
  expect(screen.getByText("partial node coverage")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));
  await waitFor(() => expect(screen.getByText("Analysis completed: run_1")).toBeInTheDocument());
});

it("blocks analysis after preview failure", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse({ design_version_id: "version_1", label: "baseline" }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ error_code: "INPUT_PREVIEW_FAILED", message: "Malformed waveform", details: {}, retryable: false, artifact_refs: [] }), { status: 422, headers: { "Content-Type": "application/json" } }));
  renderPage();
  fireEvent.change(screen.getByLabelText("Waveform CSV"), { target: { files: [new File(["bad"], "bad.csv")] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview failed")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Run analysis" })).toBeDisabled();
});

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ schema_version: "1.0", data }), { status, headers: { "Content-Type": "application/json" } });
}
