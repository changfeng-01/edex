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
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
