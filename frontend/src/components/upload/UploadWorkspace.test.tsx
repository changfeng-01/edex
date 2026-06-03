import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadWorkspace } from "./UploadWorkspace";

describe("UploadWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("renders the upload area and required waveform boundary", () => {
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    expect(screen.getByRole("heading", { name: /Upload-to-Dashboard/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run Built-in Demo/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preview Input/ })).toBeInTheDocument();
    expect(screen.getByText(/waveform.csv/)).toBeInTheDocument();
    expect(screen.getByText(/必需/)).toBeInTheDocument();
    expect(screen.getByText(/simulation_only/)).toBeInTheDocument();
    expect(screen.queryByText(/silicon verified/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/physical validation achieved/i)).not.toBeInTheDocument();
  });

  it("does not submit without waveform.csv", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ case_id: "unused" }));
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    fireEvent.click(screen.getByRole("button", { name: /Run Analysis/ }));

    expect(await screen.findByText(/请先上传 waveform.csv/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not preview without waveform.csv", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ case_id: "unused" }));
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    fireEvent.click(screen.getByRole("button", { name: /Preview Input/ }));

    expect(await screen.findByText(/Please upload waveform.csv before preview/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts preview upload and renders the input preview panel", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        case_id: "previewed_case",
        status: "preview_ready",
        evidence_boundary: evidenceBoundary(),
        preview: previewPayload({
          warnings: ["Missing configured output nodes."],
          errors: ["params.yaml could not be parsed"],
          suggestions: ["Use output columns such as v(o1)."],
          ready_for_analysis: false,
        }),
      }),
    );
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    const waveform = new File(["XVAL,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/waveform.csv/), { target: { files: [waveform] } });
    fireEvent.click(screen.getByRole("button", { name: /Preview Input/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "https://api.example.test/api/cases/preview",
        expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      );
    });
    expect(await screen.findByRole("heading", { name: /Input Preview/ })).toBeInTheDocument();
    expect(screen.getByText(/Needs input fixes/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing configured output nodes/)).toBeInTheDocument();
    expect(screen.getByText(/params.yaml could not be parsed/)).toBeInTheDocument();
    expect(screen.getByText(/Use output columns such as v\(o1\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/data_source = real_simulation_csv/).length).toBeGreaterThan(0);
    expect(window.location.search).toBe("?case_id=previewed_case");
  });

  it("uses the preview case_id for the later analysis request", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          case_id: "generated_preview_case",
          status: "preview_ready",
          evidence_boundary: evidenceBoundary(),
          preview: previewPayload(),
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          case_id: "generated_preview_case",
          status: "completed",
          bundle_url: "/api/cases/generated_preview_case/bundle",
        }),
      );
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    const waveform = new File(["XVAL,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/waveform.csv/), { target: { files: [waveform] } });
    fireEvent.click(screen.getByRole("button", { name: /Preview Input/ }));
    await screen.findByText(/Ready for analysis/i);

    fireEvent.click(screen.getByRole("button", { name: /Run Analysis/ }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const analysisBody = fetchMock.mock.calls[1][1]?.body as FormData;
    expect(analysisBody.get("case_id")).toBe("generated_preview_case");
    await waitFor(() => {
      expect(window.location.search).toBe("?case_id=generated_preview_case");
    });
  });

  it("posts multipart upload and redirects to the created case", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        case_id: "uploaded_case",
        status: "completed",
        bundle_url: "/api/cases/uploaded_case/bundle",
      }),
    );
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" />);

    const waveform = new File(["XVAL,v(o1)\n0,0\n"], "waveform.csv", { type: "text/csv" });
    const input = screen.getByLabelText(/waveform.csv/);
    fireEvent.change(input, { target: { files: [waveform] } });
    fireEvent.change(screen.getByLabelText(/case_id/), { target: { value: "uploaded_case" } });
    fireEvent.click(screen.getByRole("button", { name: /Run Analysis/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "https://api.example.test/api/cases",
        expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      );
    });
    await waitFor(() => {
      expect(window.location.search).toBe("?case_id=uploaded_case");
    });
  });

  it("runs the built-in demo and redirects to the created case", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        case_id: "demo_20260602_120000",
        status: "completed",
        bundle_url: "/api/cases/demo_20260602_120000/bundle",
      }),
    );
    const onCaseCreated = vi.fn();
    render(<UploadWorkspace apiBaseUrl="https://api.example.test" onCaseCreated={onCaseCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /Run Built-in Demo/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "https://api.example.test/api/demo/sample-case",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(window.location.search).toBe("?case_id=demo_20260602_120000");
    });
    expect(onCaseCreated).toHaveBeenCalledWith("demo_20260602_120000");
    expect(screen.queryByText(/silicon verified/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/physical validation achieved/i)).not.toBeInTheDocument();
  });
});

function evidenceBoundary() {
  return {
    data_source: "real_simulation_csv",
    engineering_validity: "simulation_only",
    must_resimulate: true,
  };
}

function previewPayload(overrides: Record<string, unknown> = {}) {
  return {
    ready_for_analysis: true,
    row_count: 2,
    column_count: 2,
    time_column_original: "XVAL",
    time_column_normalized: "time",
    time_min: 0,
    time_max: 1,
    time_span: 1,
    guessed_time_unit: "s",
    voltage_min: 0,
    voltage_max: 1,
    detected_output_nodes: ["o1"],
    detected_output_node_count: 1,
    sample_output_nodes: ["o1"],
    missing_configured_nodes: [],
    params_summary: {
      exists: true,
      parameter_count: 1,
      parameter_names: ["capacitance"],
      has_param_space: true,
    },
    netlist_summary: {
      netlist_available: true,
      mos_like_device_count: 2,
      capacitor_like_count: 1,
      resistor_like_count: 1,
      subckt_count: 1,
    },
    attachments_summary: {
      image_count: 1,
      image_analysis_enabled: false,
    },
    warnings: [],
    errors: [],
    suggestions: [],
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
