import fs from "node:fs";
import path from "node:path";
import { detectOmegaRunV18, findSeriesMembersV18 } from "./run_scan_v18";

export type ResolvedRun =
  | { kind: "single"; runAbs: string; runId: string }
  | { kind: "series"; seriesId: string; members: Array<{ tick_u64: number; runId: string; runAbs: string }> };

function isDirNoSymlink(abs: string): boolean {
  try {
    const st = fs.lstatSync(abs);
    if (st.isSymbolicLink()) {
      return false;
    }
    return st.isDirectory();
  } catch {
    return false;
  }
}

export function resolveRunV18(runsRootAbs: string, runId: string): ResolvedRun | null {
  const singleAbs = path.join(runsRootAbs, runId);
  if (isDirNoSymlink(singleAbs) && detectOmegaRunV18(singleAbs)) {
    return { kind: "single", runAbs: singleAbs, runId };
  }

  const members = findSeriesMembersV18(runsRootAbs, runId).map((row) => ({
    tick_u64: row.tick_u64,
    runId: row.run_id,
    runAbs: row.abs_path,
  }));
  if (members.length === 0) {
    return null;
  }
  return {
    kind: "series",
    seriesId: runId,
    members,
  };
}

export function selectSeriesMember(
  members: Array<{ tick_u64: number; runId: string; runAbs: string }>,
  tick?: number,
): { tick_u64: number; runId: string; runAbs: string } | null {
  if (members.length === 0) {
    return null;
  }
  if (typeof tick !== "number") {
    return members[members.length - 1];
  }
  const wanted = Math.floor(tick);
  const found = members.find((row) => row.tick_u64 === wanted);
  return found ?? null;
}
