import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductApiError, createProductClient } from "./productClient";


afterEach(() => vi.restoreAllMocks());

describe("productClient", () => {
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
});
