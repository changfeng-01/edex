import { describe, expect, it } from "vitest";

import { parseMetricRows, parseOptimizationRows, toMicroseconds, toPercent } from "./loaders";

describe("dashboard data loaders", () => {
  it("parses metric rows into numeric trend points", () => {
    const rows = parseMetricRows(
      [
        "stage,node,VOH_mean,Delay,Ripple,OverlapRatio",
        "1,o1,6.15,,0.1,0.3333333333",
        "2,o2,6.2,0.000002,0.2,0.25",
      ].join("\n"),
    );

    expect(rows).toEqual([
      {
        stage: 1,
        node: "o1",
        voh: 6.15,
        delayUs: null,
        ripple: 0.1,
        overlapRatio: 0.3333333333,
      },
      {
        stage: 2,
        node: "o2",
        voh: 6.2,
        delayUs: 2,
        ripple: 0.2,
        overlapRatio: 0.25,
      },
    ]);
  });

  it("parses optimization rows for the snapshot table", () => {
    const rows = parseOptimizationRows(
      [
        "run_id,Overall_status,overall_score,Max_overlap_ratio,data_source,engineering_validity",
        "real_1,FAIL_OVERLAP,62,0.3333333333,real_simulation_csv,simulation_only",
      ].join("\n"),
    );

    expect(rows[0]).toMatchObject({
      runId: "real_1",
      status: "FAIL_OVERLAP",
      score: 62,
      maxOverlapRatio: 0.3333333333,
      dataSource: "real_simulation_csv",
      engineeringValidity: "simulation_only",
    });
  });

  it("formats seconds and ratios for dashboard display", () => {
    expect(toMicroseconds(0.000002)).toBe("2.00 us");
    expect(toMicroseconds(null)).toBe("N/A");
    expect(toPercent(0.3333333333)).toBe("33.3%");
  });
});
