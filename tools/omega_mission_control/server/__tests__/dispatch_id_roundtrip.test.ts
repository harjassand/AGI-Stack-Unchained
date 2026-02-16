import { afterEach, describe, expect, it } from "vitest";
import { promotionBundleForDispatch } from "../artifacts_v18";
import { resolveRunV18 } from "../run_resolve_v18";
import { formatSeriesDispatchId, parseSeriesDispatchId } from "../series_dispatch_v18";
import { createOmegaRun, mkTempRunsRoot, rmTree } from "./test_utils";

const temps: string[] = [];

afterEach(() => {
  for (const dir of temps.splice(0)) {
    rmTree(dir);
  }
});

describe("series dispatch id roundtrip", () => {
  it("parses tNNNN_dispatch and resolves promotion bundle against member tick", () => {
    const runsRoot = mkTempRunsRoot("omega-mc-dispatch-id-");
    temps.push(runsRoot);

    createOmegaRun(runsRoot, "weekend_roundtrip_tick_0003", { tick_u64: 3, dispatch_dir: "abc123" });
    createOmegaRun(runsRoot, "weekend_roundtrip_tick_0004", { tick_u64: 4, dispatch_dir: "def456" });

    const seriesDispatchId = formatSeriesDispatchId(3, "abc123");
    expect(seriesDispatchId).toBe("t0003_abc123");

    const parsed = parseSeriesDispatchId(seriesDispatchId);
    expect(parsed).not.toBeNull();
    expect(parsed?.tick_u64).toBe(3);
    expect(parsed?.dispatch_dir).toBe("abc123");

    const resolved = resolveRunV18(runsRoot, "weekend_roundtrip");
    expect(resolved).not.toBeNull();
    expect(resolved?.kind).toBe("series");
    if (!resolved || resolved.kind !== "series" || !parsed) {
      return;
    }

    const member = resolved.members.find((row) => row.tick_u64 === parsed.tick_u64);
    expect(member).toBeDefined();
    if (!member) {
      return;
    }

    const payload = promotionBundleForDispatch(member.runAbs, parsed.dispatch_dir);
    expect(payload).not.toBeNull();
    expect((payload as Record<string, unknown>).bundle_payload).not.toBeNull();
  });
});
