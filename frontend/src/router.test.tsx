import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider } from "react-router-dom";

import { createAppRouter } from "./router";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("product workspace routes", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ schema_version: "1.0", data: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it.each([
    ["/workspaces/default/projects", "Projects"],
    ["/upload", "Upload analysis"],
    ["/projects/new", "Create GOA project"],
    ["/projects/project_1/overview", "Project overview"],
    ["/projects/project_1/versions/version_1", "Design version"],
    ["/analysis/run_1", "Analysis run"],
    ["/experiments/experiment_1", "Optimization experiment"],
    ["/simulation-jobs/job_1", "Manual simulation job"],
    ["/comparisons/comparison_1", "Evaluated comparison"],
    ["/demo?case_id=public_demo", "Public demo"],
  ])("routes %s to its working surface", async (path, heading) => {
    render(<RouterProvider router={createAppRouter([path])} />);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("renders a designed not-found state", async () => {
    render(<RouterProvider router={createAppRouter(["/missing"])} />);
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to projects" })).toBeInTheDocument();
  });
});
