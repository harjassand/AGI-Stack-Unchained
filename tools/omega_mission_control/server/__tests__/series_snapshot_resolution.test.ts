import { afterEach, describe, expect, it } from "vitest";
import { buildSnapshotPayload } from "../artifacts_v18";
import { resolveRunV18, selectSeriesMember } from "../run_resolve_v18";
import { createOmegaRun, mkTempRunsRoot, rmTree } from "./test_utils";

const temps: string[] = [];

afterEach(() => {
  for (const dir of temps.splice(0)) {
    rmTree(dir);
  }
});

describe("series snapshot resolution", () => {
  it("resolves snapshot tick=2 to tick_0002 member", () => {
    const runsRoot = mkTempRunsRoot("omega-mc-series-snapshot-");
    temps.push(runsRoot);

    createOmegaRun(runsRoot, "weekend_probe_tick_0001", { tick_u64: 1, dispatch_dir: "x0001" });
    createOmegaRun(runsRoot, "weekend_probe_tick_0002", { tick_u64: 2, dispatch_dir: "x0002" });

    const resolved = resolveRunV18(runsRoot, "weekend_probe");
    expect(resolved).not.toBeNull();
    expect(resolved?.kind).toBe("series");
    if (!resolved || resolved.kind !== "series") {
      return;
    }

    const member = selectSeriesMember(resolved.members, 2);
    expect(member).not.toBeNull();
    expect(member?.runId).toBe("weekend_probe_tick_0002");

    if (!member) {
      return;
    }
    const snapshot = buildSnapshotPayload(member.runAbs, 2, { include_extras: false });
    expect(snapshot.latest_snapshot).not.toBeNull();
    expect((snapshot.latest_snapshot as Record<string, unknown>).tick_u64).toBe(2);
  });
});
