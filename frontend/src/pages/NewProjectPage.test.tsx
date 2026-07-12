import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { NewProjectPage } from "./NewProjectPage";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("validates required fields beside the form", async () => {
  render(<MemoryRouter><NewProjectPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(await screen.findByText("Project name is required.")).toBeInTheDocument();
});

it("shows the exact simulation-only profile boundary", () => {
  render(<MemoryRouter><NewProjectPage /></MemoryRouter>);
  expect(screen.getByText("data_source = real_simulation_csv")).toBeInTheDocument();
  expect(screen.getByText("engineering_validity = simulation_only")).toBeInTheDocument();
  expect(screen.getByText("must_resimulate = true")).toBeInTheDocument();
  expect(screen.getByLabelText("Circuit profile")).toHaveValue("goa_8k");
});

it("creates a project through the Product API", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ schema_version: "1.0", data: { project_id: "project_1" } }), { status: 201, headers: { "Content-Type": "application/json" } }));
  render(<MemoryRouter><NewProjectPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "GOA Alpha" } });
  fireEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(await screen.findByText("Project created: project_1")).toBeInTheDocument();
});
