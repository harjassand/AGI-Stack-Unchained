import fs from "node:fs";
import path from "node:path";
import type { RunInfo, OmegaMode } from "../lib/types_v18";

const LEDGER_REL = path.join("daemon", "rsi_omega_daemon_v18_0", "state", "ledger", "omega_ledger_v1.jsonl");
const PACK_REL = path.join("daemon", "rsi_omega_daemon_v18_0", "config", "rsi_omega_daemon_pack_v1.json");
const STATE_ROOT_REL = path.join("daemon", "rsi_omega_daemon_v18_0", "state");
const IN_PROGRESS_STATE_SUBDIRS = [
  "state",
  "observations",
  "issues",
  "decisions",
  "dispatch",
  "runaway",
  "subruns",
  "snapshot",
  "ledger",
] as const;

const TICK_RUN_RE = /^(.*)_tick_(\d+)$/;

export type TickRunMember = {
  tick_u64: number;
  run_id: string;
  abs_path: string;
  last_seen_utc: string | null;
};

function isDirectoryNoSymlink(abs: string): boolean {
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

function isFileNoSymlink(abs: string): boolean {
  try {
    const st = fs.lstatSync(abs);
    if (st.isSymbolicLink()) {
      return false;
    }
    return st.isFile();
  } catch {
    return false;
  }
}

function maxMtimeRecursive(root: string): number | null {
  let best: number | null = null;
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
      } else if (entry.isFile()) {
        try {
          const mt = fs.statSync(abs).mtimeMs;
          if (best === null || mt > best) {
            best = mt;
          }
        } catch {
          // Ignore unreadable files.
        }
      }
    }
  }
  return best;
}

function toUtcIso(ms: number | null): string | null {
  if (ms === null) {
    return null;
  }
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function detectOmegaRunV18(runAbs: string): boolean {
  const packPath = path.join(runAbs, PACK_REL);
  if (!isFileNoSymlink(packPath)) {
    return false;
  }

  const ledgerPath = path.join(runAbs, LEDGER_REL);
  if (isFileNoSymlink(ledgerPath)) {
    return true;
  }

  // Include in-progress runs before first ledger append, so UI can live-follow active ticks.
  const stateRoot = path.join(runAbs, STATE_ROOT_REL);
  if (!isDirectoryNoSymlink(stateRoot)) {
    return false;
  }

  for (const sub of IN_PROGRESS_STATE_SUBDIRS) {
    const abs = path.join(stateRoot, sub);
    if (!isDirectoryNoSymlink(abs)) {
      continue;
    }
    try {
      if (fs.readdirSync(abs).length > 0) {
        return true;
      }
    } catch {
      // Ignore unreadable subtree.
    }
  }
  return false;
}

export function runLastSeenUtcV18(runAbs: string): string | null {
  const ledgerDir = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "state", "ledger");
  const snapshotDir = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "state", "snapshot");
  const a = maxMtimeRecursive(ledgerDir);
  const b = maxMtimeRecursive(snapshotDir);
  const best = a === null ? b : b === null ? a : Math.max(a, b);
  return toUtcIso(best);
}

function parseTickRunId(runId: string): { series_id: string; tick_u64: number } | null {
  const m = runId.match(TICK_RUN_RE);
  if (!m || !m[1]) {
    return null;
  }
  const tick = Number.parseInt(m[2], 10);
  if (!Number.isFinite(tick)) {
    return null;
  }
  return { series_id: m[1], tick_u64: tick };
}

function newestUtc(a: string | null, b: string | null): string | null {
  if (!a) {
    return b;
  }
  if (!b) {
    return a;
  }
  return a > b ? a : b;
}

function listOmegaRunDirs(runsRootAbs: string): Array<{ run_id: string; abs_path: string; last_seen_utc: string | null }> {
  if (!isDirectoryNoSymlink(runsRootAbs)) {
    return [];
  }

  const out: Array<{ run_id: string; abs_path: string; last_seen_utc: string | null }> = [];
  for (const entry of fs.readdirSync(runsRootAbs, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) {
      continue;
    }
    if (entry.name.startsWith(".")) {
      continue;
    }
    const abs = path.join(runsRootAbs, entry.name);
    if (!detectOmegaRunV18(abs)) {
      continue;
    }
    out.push({
      run_id: entry.name,
      abs_path: abs,
      last_seen_utc: runLastSeenUtcV18(abs),
    });
  }
  return out;
}

export function findSeriesMembersV18(runsRootAbs: string, seriesId: string): TickRunMember[] {
  const out: TickRunMember[] = [];
  for (const row of listOmegaRunDirs(runsRootAbs)) {
    const parsed = parseTickRunId(row.run_id);
    if (!parsed || parsed.series_id !== seriesId) {
      continue;
    }
    out.push({
      tick_u64: parsed.tick_u64,
      run_id: row.run_id,
      abs_path: row.abs_path,
      last_seen_utc: row.last_seen_utc,
    });
  }
  out.sort((a, b) => a.tick_u64 - b.tick_u64 || a.run_id.localeCompare(b.run_id));
  return out;
}

type ScanRunsOpts = {
  include_ticks?: boolean;
  include_members?: boolean;
};

export function scanRunsRootV18(runsRootAbs: string, mode: OmegaMode, opts: ScanRunsOpts = {}): RunInfo[] {
  const includeTicks = opts.include_ticks === true;
  const includeMembers = opts.include_members === true;
  const raw = listOmegaRunDirs(runsRootAbs);
  const seriesMembers = new Map<string, TickRunMember[]>();
  const singleCandidates: Array<{ run_id: string; abs_path: string; last_seen_utc: string | null }> = [];

  for (const row of raw) {
    const parsed = parseTickRunId(row.run_id);
    if (!parsed) {
      singleCandidates.push(row);
      continue;
    }
    const bucket = seriesMembers.get(parsed.series_id) ?? [];
    bucket.push({
      tick_u64: parsed.tick_u64,
      run_id: row.run_id,
      abs_path: row.abs_path,
      last_seen_utc: row.last_seen_utc,
    });
    seriesMembers.set(parsed.series_id, bucket);
  }

  const seriesRuns: RunInfo[] = [];
  const rawTickSingles: RunInfo[] = [];
  for (const [seriesId, membersUnsorted] of seriesMembers.entries()) {
    const members = [...membersUnsorted].sort((a, b) => a.tick_u64 - b.tick_u64 || a.run_id.localeCompare(b.run_id));
    if (members.length < 2) {
      singleCandidates.push({
        run_id: members[0].run_id,
        abs_path: members[0].abs_path,
        last_seen_utc: members[0].last_seen_utc,
      });
      continue;
    }

    let lastSeen: string | null = null;
    for (const member of members) {
      lastSeen = newestUtc(lastSeen, member.last_seen_utc);
      if (includeTicks) {
        rawTickSingles.push({
          run_id: member.run_id,
          kind: "single",
          abs_path: member.abs_path,
          last_seen_utc: member.last_seen_utc,
          mode,
        });
      }
    }

    seriesRuns.push({
      run_id: seriesId,
      kind: "series",
      abs_path: null,
      members: includeMembers ? members.map((m) => ({ tick_u64: m.tick_u64, run_id: m.run_id, abs_path: m.abs_path })) : undefined,
      tick_min_u64: members[0].tick_u64,
      tick_max_u64: members[members.length - 1].tick_u64,
      tick_count: members.length,
      last_seen_utc: lastSeen,
      mode,
    });
  }

  const singles: RunInfo[] = singleCandidates.map((row) => ({
    run_id: row.run_id,
    kind: "single",
    abs_path: row.abs_path,
    last_seen_utc: row.last_seen_utc,
    mode,
  }));

  const byLastSeenDesc = (a: { last_seen_utc: string | null; run_id: string }, b: { last_seen_utc: string | null; run_id: string }): number => {
    const aSeen = a.last_seen_utc ?? "";
    const bSeen = b.last_seen_utc ?? "";
    if (aSeen !== bSeen) {
      return bSeen.localeCompare(aSeen);
    }
    return a.run_id.localeCompare(b.run_id);
  };

  seriesRuns.sort(byLastSeenDesc);
  singles.sort(byLastSeenDesc);
  rawTickSingles.sort(byLastSeenDesc);

  return [...seriesRuns, ...singles, ...rawTickSingles];
}

export function stateRootForRun(runAbs: string): string {
  return path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "state");
}

export function configRootForRun(runAbs: string): string {
  return path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "config");
}

export function ledgerPathForRun(runAbs: string): string {
  return path.join(stateRootForRun(runAbs), "ledger", "omega_ledger_v1.jsonl");
}
