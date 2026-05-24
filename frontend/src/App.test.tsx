import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
});

describe("CircuitPilot dashboard", () => {
  it("keeps status, score, and simulation boundary visible in the first screen", async () => {
    render(<App />);

    expect(await screen.findByText(/CircuitPilot/)).toBeInTheDocument();
    expect(screen.getAllByText(/FAIL_OVERLAP/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/simulation_only/).length).toBeGreaterThan(0);
    expect(screen.getByText(/不是实物测试结论/)).toBeInTheDocument();
  });

  it("presents the 16:9 command screen with a primary waveform anchor", async () => {
    render(<App />);

    expect(await screen.findByRole("region", { name: "16:9 展示大屏" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /o1 到 o8 主输出波形/ })).toHaveAttribute(
      "src",
      "/data/figures/o1_o8_overview.png",
    );
    expect(screen.getByText(/Overlap risk/)).toBeInTheDocument();
  });
});
