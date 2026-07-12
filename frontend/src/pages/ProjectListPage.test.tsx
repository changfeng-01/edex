import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ProjectListPage } from "./ProjectListPage";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  return render(<MemoryRouter><ProjectListPage /></MemoryRouter>);
}

it("shows loading then an actionable empty state", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
  renderPage();

  expect(screen.getByLabelText("Loading projects")).toBeInTheDocument();
  expect(await screen.findByText("No GOA projects yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Create first project" })).toHaveAttribute("href", "/projects/new");
  expect(screen.getByRole("link", { name: "Open public demo" })).toHaveAttribute("href", "/demo");
});

it("keeps structured failures visible", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(errorResponse("WORKSPACE_NOT_FOUND"));
  renderPage();
  expect(await screen.findByText("WORKSPACE_NOT_FOUND")).toBeInTheDocument();
});

it("renders populated projects as a compact operational list", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([
    {
      project_id: "project_very_long_identifier_123456789",
      workspace_id: "default",
      name: "720-stage GOA",
      circuit_profile_id: "goa_8k",
      spec_revision_id: "spec_v1",
      status: "active",
      created_at: "2026-07-12T00:00:00+00:00",
    },
  ]));
  renderPage();
  expect(await screen.findByRole("link", { name: "720-stage GOA" })).toBeInTheDocument();
  expect(screen.getByText("goa_8k")).toBeInTheDocument();
});

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({ schema_version: "1.0", data }), { status: 200, headers: { "Content-Type": "application/json" } });
}

function errorResponse(errorCode: string): Response {
  return new Response(JSON.stringify({ error_code: errorCode, message: "Not found", details: {}, retryable: false, artifact_refs: [] }), { status: 404, headers: { "Content-Type": "application/json" } });
}
