import type { RunInfo } from "./types_v18";

export type TickRunRef = {
  seriesId: string;
  tick: number;
  runId: string;
};

export type RunSeries = {
  seriesId: string;
  runCount: number;
  latestTick: number;
  latestRunId: string;
  lastSeenUtc: string | null;
  mode: RunInfo["mode"];
  runs: Array<{ runId: string; tick: number; lastSeenUtc: string | null }>;
};

const TICK_RUN_RE = /^(.*)_tick_(\d{1,20})$/;

export function parseTickRunId(runId: string): TickRunRef | null {
  const m = runId.match(TICK_RUN_RE);
  if (!m) {
    return null;
  }
  const seriesId = m[1];
  const tick = Number.parseInt(m[2], 10);
  if (!seriesId || !Number.isFinite(tick)) {
    return null;
  }
  return { seriesId, tick, runId };
}

function newestUtc(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return a > b ? a : b;
}

export function buildRunSeries(runs: RunInfo[]): RunSeries[] {
  const bySeries = new Map<string, RunSeries>();

  for (const run of runs) {
    const parsed = parseTickRunId(run.run_id);
    if (!parsed) {
      continue;
    }

    const current = bySeries.get(parsed.seriesId);
    const row = {
      runId: parsed.runId,
      tick: parsed.tick,
      lastSeenUtc: run.last_seen_utc,
    };

    if (!current) {
      bySeries.set(parsed.seriesId, {
        seriesId: parsed.seriesId,
        runCount: 1,
        latestTick: parsed.tick,
        latestRunId: parsed.runId,
        lastSeenUtc: run.last_seen_utc,
        mode: run.mode,
        runs: [row],
      });
      continue;
    }

    current.runCount += 1;
    current.runs.push(row);
    current.lastSeenUtc = newestUtc(current.lastSeenUtc, run.last_seen_utc);
    if (parsed.tick > current.latestTick || (parsed.tick === current.latestTick && parsed.runId > current.latestRunId)) {
      current.latestTick = parsed.tick;
      current.latestRunId = parsed.runId;
      current.mode = run.mode;
    }
  }

  const out = Array.from(bySeries.values());
  for (const series of out) {
    series.runs.sort((a, b) => b.tick - a.tick || b.runId.localeCompare(a.runId));
  }
  out.sort((a, b) => b.latestTick - a.latestTick || b.seriesId.localeCompare(a.seriesId));
  return out;
}

export function findRunSeries(runs: RunInfo[], seriesId: string): RunSeries | null {
  return buildRunSeries(runs).find((row) => row.seriesId === seriesId) ?? null;
}

