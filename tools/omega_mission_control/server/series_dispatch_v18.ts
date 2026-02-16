export const DISPATCH_DIR_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;
const SERIES_DISPATCH_PATTERN = /^t(\d+)_([A-Za-z0-9._-]{1,128})$/;

export type SeriesDispatchRef = {
  tick_u64: number;
  dispatch_dir: string;
};

export function formatSeriesDispatchId(tick_u64: number, dispatchDir: string): string {
  if (!Number.isFinite(tick_u64) || tick_u64 < 0) {
    throw new Error("INVALID_TICK");
  }
  if (!DISPATCH_DIR_PATTERN.test(dispatchDir)) {
    throw new Error("INVALID_DISPATCH_DIR");
  }
  return `t${String(Math.floor(tick_u64)).padStart(4, "0")}_${dispatchDir}`;
}

export function parseSeriesDispatchId(dispatchId: string): SeriesDispatchRef | null {
  const m = dispatchId.match(SERIES_DISPATCH_PATTERN);
  if (!m) {
    return null;
  }
  const tick = Number.parseInt(m[1], 10);
  if (!Number.isFinite(tick) || tick < 0) {
    return null;
  }
  return {
    tick_u64: Math.floor(tick),
    dispatch_dir: m[2],
  };
}
