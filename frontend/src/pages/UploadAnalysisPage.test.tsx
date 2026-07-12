import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { StrictMode } from "react";

import { UploadAnalysisPage } from "./UploadAnalysisPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<UploadAnalysisPage />} />
        <Route path="/analysis/:runId" element={<h1>Analysis destination</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

it("initializes Local Workspace when none exists", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url === "/api/v1/workspaces" && init?.method === "POST") {
      return Promise.resolve(jsonResponse(workspace("workspace_local", "Local Workspace"), 201));
    }
    if (url === "/api/v1/workspaces") return Promise.resolve(jsonResponse([]));
    return Promise.resolve(jsonResponse([]));
  });

  render(
    <StrictMode>
      <MemoryRouter initialEntries={["/upload"]}>
        <Routes><Route path="/upload" element={<UploadAnalysisPage />} /></Routes>
      </MemoryRouter>
    </StrictMode>,
  );

  expect(await screen.findByDisplayValue("Local Workspace")).toBeInTheDocument();
  const createCalls = fetchSpy.mock.calls.filter(([url, init]) => String(url) === "/api/v1/workspaces" && init?.method === "POST");
  expect(createCalls).toHaveLength(1);
  expect(createCalls[0]?.[1]).toEqual(expect.objectContaining({ body: JSON.stringify({ name: "Local Workspace" }) }));
});

it("shows a workspace selector when multiple workspaces exist", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([
    workspace("workspace_1", "Display lab"),
    workspace("workspace_2", "Timing lab"),
  ]));

  renderPage();

  const selector = await screen.findByLabelText("Workspace");
  expect(selector).toHaveDisplayValue("Select workspace");
  expect(screen.getByRole("option", { name: "Display lab" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Timing lab" })).toBeInTheDocument();
});

it("validates version, waveform, and params before creating context", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([project("project_1", "workspace_1", "GOA baseline")]));

  renderPage();
  await screen.findByDisplayValue("GOA baseline");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));

  expect(screen.getByText("Design version name is required.")).toBeInTheDocument();
  expect(screen.getByText("Waveform CSV is required.")).toBeInTheDocument();
  expect(screen.getByText("Parameter YAML is required.")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("creates a new project and auto-runs a clean preview before navigating", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(jsonResponse(project("project_new", "workspace_1", "New GOA"), 201))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_new"), 201))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready"), 201))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_1", status: "running" }, 201));

  renderPage();
  await screen.findByLabelText("New project name");
  fireEvent.change(screen.getByLabelText("New project name"), { target: { value: "New GOA" } });
  fillRequiredInputs("baseline-01");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));

  expect(await screen.findByRole("heading", { name: "Analysis destination" })).toBeInTheDocument();
  expect(JSON.parse(String(fetchSpy.mock.calls[2]?.[1]?.body))).toEqual({
    workspace_id: "workspace_1",
    name: "New GOA",
    circuit_profile_id: "goa_8k",
    spec_revision_id: "spec_v1",
  });
});

it("waits for confirmation when preview contains warnings", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([project("project_1", "workspace_1", "GOA baseline")]))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_1"), 201))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready_with_warnings", ["partial node coverage"]), 201))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_1", status: "completed" }, 201));

  renderPage();
  await screen.findByDisplayValue("GOA baseline");
  fillRequiredInputs("warning-run");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));

  expect(await screen.findByText("partial node coverage")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(4);
  fireEvent.click(screen.getByRole("button", { name: "Confirm and run" }));
  expect(await screen.findByRole("heading", { name: "Analysis destination" })).toBeInTheDocument();
});

it("preserves files and reuses the created version after a preview failure", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([project("project_1", "workspace_1", "GOA baseline")]))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_1"), 201))
    .mockResolvedValueOnce(errorResponse("Malformed waveform"))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready"), 201))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_1", status: "completed" }, 201));

  renderPage();
  await screen.findByDisplayValue("GOA baseline");
  fillRequiredInputs("retry-run");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview failed")).toBeInTheDocument();
  expect(screen.getByText("waveform.csv selected")).toBeInTheDocument();
  expect(screen.getByText("params.yaml selected")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
  expect(await screen.findByRole("heading", { name: "Analysis destination" })).toBeInTheDocument();
  const versionCalls = fetchSpy.mock.calls.filter(([url]) => /\/projects\/[^/]+\/design-versions$/.test(String(url)));
  expect(versionCalls).toHaveLength(1);
});

it("retries analysis without rebuilding the preview or version", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([project("project_1", "workspace_1", "GOA baseline")]))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_1"), 201))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready"), 201))
    .mockResolvedValueOnce(errorResponse("Analysis service unavailable", "ANALYSIS_EXECUTION_FAILED", 500))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_2", status: "running" }, 201));

  renderPage();
  await screen.findByDisplayValue("GOA baseline");
  fillRequiredInputs("analysis-retry");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Analysis failed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry analysis" }));

  expect(await screen.findByRole("heading", { name: "Analysis destination" })).toBeInTheDocument();
  expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith("/inputs/preview"))).toHaveLength(1);
  expect(fetchSpy.mock.calls.filter(([url]) => /\/projects\/[^/]+\/design-versions$/.test(String(url)))).toHaveLength(1);
});

it("reuses a newly persisted project when version creation must be retried", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(jsonResponse(project("project_new", "workspace_1", "New GOA"), 201))
    .mockResolvedValueOnce(errorResponse("Version creation failed", "INPUT_PREVIEW_FAILED", 500))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_new"), 201))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready"), 201))
    .mockResolvedValueOnce(jsonResponse({ analysis_run_id: "run_1", status: "running" }, 201));

  renderPage();
  await screen.findByLabelText("New project name");
  fireEvent.change(screen.getByLabelText("New project name"), { target: { value: "New GOA" } });
  fillRequiredInputs("version-retry");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByText("Preview failed")).toBeInTheDocument();
  expect(screen.getByLabelText("New project name")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));

  expect(await screen.findByRole("heading", { name: "Analysis destination" })).toBeInTheDocument();
  expect(fetchSpy.mock.calls.filter(([url]) => String(url) === "/api/v1/projects")).toHaveLength(1);
});

it("invalidates a warned preview when an input file changes", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse([workspace("workspace_1", "Display lab")]))
    .mockResolvedValueOnce(jsonResponse([project("project_1", "workspace_1", "GOA baseline")]))
    .mockResolvedValueOnce(jsonResponse(version("version_1", "project_1"), 201))
    .mockResolvedValueOnce(jsonResponse(snapshot("preview_ready_with_warnings", ["partial node coverage"]), 201));

  renderPage();
  await screen.findByDisplayValue("GOA baseline");
  fillRequiredInputs("stale-preview");
  fireEvent.click(screen.getByRole("button", { name: "Preview input" }));
  expect(await screen.findByRole("button", { name: "Confirm and run" })).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Waveform CSV"), {
    target: { files: [new File(["time,v(o1)\n0,1\n"], "changed.csv", { type: "text/csv" })] },
  });
  expect(screen.queryByRole("button", { name: "Confirm and run" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Preview input" })).toBeInTheDocument();
});

function fillRequiredInputs(label: string) {
  fireEvent.change(screen.getByLabelText("Design version name"), { target: { value: label } });
  fireEvent.change(screen.getByLabelText("Waveform CSV"), {
    target: { files: [new File(["time,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" })] },
  });
  fireEvent.change(screen.getByLabelText("Parameter YAML"), {
    target: { files: [new File(["clock_period_us: 16.7\n"], "params.yaml", { type: "application/yaml" })] },
  });
}

function workspace(workspaceId: string, name: string) {
  return { workspace_id: workspaceId, name, created_at: "2026-07-12T00:00:00Z" };
}

function project(projectId: string, workspaceId: string, name: string) {
  return { project_id: projectId, workspace_id: workspaceId, name, circuit_profile_id: "goa_8k", spec_revision_id: "spec_v1", status: "active", created_at: "2026-07-12T00:00:00Z" };
}

function version(versionId: string, projectId: string) {
  return { design_version_id: versionId, project_id: projectId, label: "baseline", created_at: "2026-07-12T00:00:00Z" };
}

function snapshot(status: string, warnings: string[] = []) {
  return {
    input_snapshot_id: "input_1",
    preview_status: status,
    preview: { warnings },
    manifest_ref: { uri: "artifact://input/manifest.json", key: "input/manifest.json", size_bytes: 10, sha256: "a".repeat(64) },
  };
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ schema_version: "1.0", data }), { status, headers: { "Content-Type": "application/json" } });
}

function errorResponse(message: string, errorCode = "INPUT_PREVIEW_FAILED", status = 422): Response {
  return new Response(JSON.stringify({ error_code: errorCode, message, details: {}, retryable: false, artifact_refs: [] }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
