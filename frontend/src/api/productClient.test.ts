import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductApiError, createProductClient } from "./productClient";


afterEach(() => vi.restoreAllMocks());

describe("productClient", () => {
  it("lists workspaces from the versioned product API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ schema_version: "1.0", data: [{ workspace_id: "workspace_1", name: "GOA team" }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const workspaces = await createProductClient("http://api.test").listWorkspaces();

    expect(workspaces).toEqual([{ workspace_id: "workspace_1", name: "GOA team" }]);
    expect(fetch).toHaveBeenCalledWith("http://api.test/api/v1/workspaces", expect.any(Object));
  });

  it("creates a workspace with a JSON product contract", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ schema_version: "1.0", data: { workspace_id: "workspace_1", name: "Local Workspace" } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await createProductClient("http://api.test").createWorkspace("Local Workspace");

    expect(fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/workspaces",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Local Workspace" }) }),
    );
  });

  it("creates a design version under the selected project", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ schema_version: "1.0", data: { design_version_id: "version_1", label: "baseline" } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await createProductClient("http://api.test").createDesignVersion("project_1", { label: "baseline" });

    expect(fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/projects/project_1/design-versions",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ label: "baseline" }) }),
    );
  });

  it("unwraps versioned success responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ schema_version: "1.0", data: [{ project_id: "project_1" }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const projects = await createProductClient("http://api.test").listProjects("workspace_1");

    expect(projects).toEqual([{ project_id: "project_1" }]);
    expect(fetch).toHaveBeenCalledWith("http://api.test/api/v1/workspaces/workspace_1/projects", expect.any(Object));
  });

  it("preserves structured product errors without flattening details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error_code: "INPUT_PREVIEW_FAILED",
          message: "Input preview failed.",
          details: { preview: { errors: ["missing node"] } },
          retryable: false,
          artifact_refs: ["artifact://preview/log.json"],
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(createProductClient().getProject("project_bad")).rejects.toEqual(
      expect.objectContaining({
        errorCode: "INPUT_PREVIEW_FAILED",
        details: { preview: { errors: ["missing node"] } },
        retryable: false,
        artifactRefs: ["artifact://preview/log.json"],
      }),
    );
  });

  it("calls Phase 2 experiment, job, and comparison contracts", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ schema_version: "1.0", data: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = createProductClient("http://api.test");
    await client.approveCandidate("candidate_1", "reviewer");
    await client.exportSimulationJob("job_1");
    await client.getComparison("comparison_1");

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/v1/candidates/candidate_1:approve",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "http://api.test/api/v1/simulation-jobs/job_1:export",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "http://api.test/api/v1/comparisons/comparison_1",
      expect.any(Object),
    );
  });
});
