import { afterEach, describe, expect, it } from "vitest";
import { scanRunsRootV18 } from "../run_scan_v18";
import { createOmegaRun, mkTempRunsRoot, rmTree } from "./test_utils";

const temps: string[] = [];

afterEach(() => {
  for (const dir of temps.splice(0)) {
    rmTree(dir);
  }
});

describe("series grouping", () => {
  it("groups tick runs as one series and keeps standalone run as single", () => {
    const runsRoot = mkTempRunsRoot("omega-mc-series-grouping-");
    temps.push(runsRoot);

    createOmegaRun(runsRoot, "weekend_run_tick_0001", { tick_u64: 1, dispatch_dir: "d0001" });
    createOmegaRun(runsRoot, "weekend_run_tick_0002", { tick_u64: 2, dispatch_dir: "d0002" });
    createOmegaRun(runsRoot, "standalone_run_alpha", { tick_u64: 11, dispatch_dir: "d0011" });

    const grouped = scanRunsRootV18(runsRoot, "fs");
    const series = grouped.filter((row) => row.kind === "series");
    const singles = grouped.filter((row) => row.kind === "single");

    expect(series).toHaveLength(1);
    expect(series[0].run_id).toBe("weekend_run");
    expect(series[0].tick_count).toBe(2);
    expect(series[0].tick_min_u64).toBe(1);
    expect(series[0].tick_max_u64).toBe(2);

    expect(singles).toHaveLength(1);
    expect(singles[0].run_id).toBe("standalone_run_alpha");
  });
});
