"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchRuns, fetchSnapshot } from "../../lib/api";
import { findRunSeries } from "../../lib/run_series";
import type { RunInfo } from "../../lib/types_v18";
import OmegaDashboard from "./OmegaDashboard";

type RunMetricSummary = {
  last: number | null;
  best: number | null;
  escalation: number;
};

type RunSummary = {
  runId: string;
  tick: number;
  actionKind: string;
  campaignId: string | null;
  selectedMetricId: string | null;
  escalationLevel: number;
  versionMinor: number | null;
  promotionStatus: string | null;
  activationPass: boolean;
  metrics: Record<string, RunMetricSummary>;
};

const RECENT_WINDOW = 30;
const FETCH_BATCH = 8;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function q32ToNumber(value: unknown): number | null {
  const rec = asRecord(value);
  if (!rec) {
    return null;
  }
  const q = asNumber(rec.q);
  if (q === null) {
    return null;
  }
  return q / 2 ** 32;
}

function extractRunSummary(runId: string, payload: Record<string, unknown>): RunSummary {
  const artifacts = asRecord(payload.artifacts);
  const decision = asRecord(artifacts?.omega_decision_plan_v1);
  const promotion = asRecord(artifacts?.omega_promotion_receipt_v1);
  const activation = asRecord(artifacts?.omega_activation_receipt_v1);
  const runawayState = asRecord(artifacts?.omega_runaway_state_v1);
  const latestSnapshot = asRecord(payload.latest_snapshot);
  const metricStates = asRecord(runawayState?.metric_states);

  const metrics: Record<string, RunMetricSummary> = {};
  if (metricStates) {
    for (const [metricId, rowRaw] of Object.entries(metricStates)) {
      const row = asRecord(rowRaw);
      if (!row) {
        continue;
      }
      metrics[metricId] = {
        last: q32ToNumber(row.last_value_q32),
        best: q32ToNumber(row.best_value_q32),
        escalation: Math.floor(asNumber(row.escalation_level_u64) ?? 0),
      };
    }
  }

  return {
    runId,
    tick: Math.floor(asNumber(latestSnapshot?.tick_u64) ?? 0),
    actionKind: asString(decision?.action_kind) ?? "NOOP",
    campaignId: asString(decision?.campaign_id) ?? null,
    selectedMetricId: asString(decision?.runaway_selected_metric_id) ?? null,
    escalationLevel: Math.floor(asNumber(decision?.runaway_escalation_level_u64) ?? 0),
    versionMinor: asNumber(runawayState?.version_minor_u64),
    promotionStatus: asString(asRecord(promotion?.result)?.status) ?? null,
    activationPass: activation?.pass === true,
    metrics,
  };
}

function formatRatio(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return `${value.toFixed(3)}x`;
}

export default function OmegaSeriesDashboard({ seriesId }: { seriesId: string }) {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [summaryByRunId, setSummaryByRunId] = useState<Record<string, RunSummary>>({});
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const summaryInFlightRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetchRuns(true);
        if (!active) {
          return;
        }
        setRuns(res.runs);
        setError(null);
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load runs");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    const timer = setInterval(() => void load(), 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const series = useMemo(() => findRunSeries(runs, seriesId), [runs, seriesId]);
  const recentRunIds = useMemo(() => (series ? series.runs.slice(0, RECENT_WINDOW).map((row) => row.runId) : []), [series]);
  const missingSummaryIds = useMemo(() => recentRunIds.filter((runId) => !summaryByRunId[runId]), [recentRunIds, summaryByRunId]);
  const batchToFetch = useMemo(() => missingSummaryIds.slice(0, FETCH_BATCH), [missingSummaryIds]);
  const recentSummariesDesc = useMemo(
    () => recentRunIds.map((runId) => summaryByRunId[runId]).filter((row): row is RunSummary => !!row),
    [recentRunIds, summaryByRunId],
  );
  const recentSummariesAsc = useMemo(() => [...recentSummariesDesc].sort((a, b) => a.tick - b.tick || a.runId.localeCompare(b.runId)), [recentSummariesDesc]);

  useEffect(() => {
    if (batchToFetch.length === 0) {
      return;
    }
    const toFetch = batchToFetch.filter((runId) => !summaryInFlightRef.current.has(runId));
    if (toFetch.length === 0) {
      return;
    }
    for (const runId of toFetch) {
      summaryInFlightRef.current.add(runId);
    }
    let active = true;
    setSummaryLoading(true);
    const loadBatch = async () => {
      const resolved = await Promise.all(
        toFetch.map(async (runId) => {
          try {
            const res = await fetchSnapshot(runId);
            return { runId, summary: extractRunSummary(runId, res.payload as unknown as Record<string, unknown>), error: null as string | null };
          } catch (err) {
            return { runId, summary: null, error: err instanceof Error ? err.message : `failed loading ${runId}` };
          }
        }),
      );
      if (!active) {
        for (const row of resolved) {
          summaryInFlightRef.current.delete(row.runId);
        }
        return;
      }
      for (const row of resolved) {
        summaryInFlightRef.current.delete(row.runId);
      }
      setSummaryByRunId((prev) => {
        const next = { ...prev };
        for (const row of resolved) {
          if (row.summary) {
            next[row.runId] = row.summary;
          }
        }
        return next;
      });
      const firstError = resolved.find((row) => row.error)?.error ?? null;
      setSummaryError(firstError);
      setSummaryLoading(false);
    };
    void loadBatch();
    return () => {
      active = false;
    };
  }, [batchToFetch]);

  useEffect(() => {
    if (!series) {
      setActiveRunId(null);
      return;
    }
    setActiveRunId((prev) => (prev === series.latestRunId ? prev : series.latestRunId));
  }, [series]);

  const campaignMix = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of recentSummariesDesc) {
      const key = row.campaignId ?? "n/a";
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return Array.from(map.entries())
      .map(([campaignId, count]) => ({ campaignId, count }))
      .sort((a, b) => b.count - a.count || a.campaignId.localeCompare(b.campaignId));
  }, [recentSummariesDesc]);

  const majorStats = useMemo(() => {
    const promotions = recentSummariesDesc.filter((row) => row.promotionStatus === "PROMOTED").length;
    const activations = recentSummariesDesc.filter((row) => row.activationPass).length;
    const escalatedTicks = recentSummariesDesc.filter((row) => row.escalationLevel > 0).length;

    let versionStart: number | null = null;
    let versionEnd: number | null = null;
    for (const row of recentSummariesAsc) {
      if (row.versionMinor === null) {
        continue;
      }
      if (versionStart === null) {
        versionStart = row.versionMinor;
      }
      versionEnd = row.versionMinor;
    }

    let bestMetric: string | null = null;
    let bestRatio: number | null = null;
    if (recentSummariesAsc.length >= 2) {
      const first = recentSummariesAsc[0];
      const metricIds = Array.from(new Set(recentSummariesAsc.flatMap((row) => Object.keys(row.metrics)))).sort();
      for (const metricId of metricIds) {
        const startVal = first.metrics[metricId]?.last ?? null;
        if (startVal === null || startVal <= 0) {
          continue;
        }
        let bestVal: number | null = null;
        for (const row of recentSummariesAsc) {
          const candidate = row.metrics[metricId]?.best ?? row.metrics[metricId]?.last ?? null;
          if (candidate === null || candidate <= 0) {
            continue;
          }
          bestVal = bestVal === null ? candidate : Math.min(bestVal, candidate);
        }
        if (bestVal === null || bestVal <= 0) {
          continue;
        }
        const ratio = startVal / bestVal;
        if (!Number.isFinite(ratio)) {
          continue;
        }
        if (bestRatio === null || ratio > bestRatio) {
          bestRatio = ratio;
          bestMetric = metricId;
        }
      }
    }

    return {
      promotions,
      activations,
      escalatedTicks,
      versionStart,
      versionEnd,
      versionDelta: versionStart !== null && versionEnd !== null ? versionEnd - versionStart : null,
      bestMetric,
      bestRatio,
    };
  }, [recentSummariesAsc, recentSummariesDesc]);

  if (loading && !series) {
    return (
      <main style={{ maxWidth: 960, margin: "0 auto", padding: 20 }}>
        <div className="card">Loading run series...</div>
      </main>
    );
  }

  if (!series || !activeRunId) {
    return (
      <main style={{ maxWidth: 960, margin: "0 auto", padding: 20 }}>
        <div className="card" style={{ marginBottom: 12 }}>
          <h1 style={{ marginTop: 0 }}>Run Series Not Found</h1>
          <p style={{ marginBottom: 0 }}>
            Could not find series <code>{seriesId}</code>. It may not exist yet or no ticks have been scanned.
          </p>
        </div>
        <Link href="/" className="btn" style={{ textDecoration: "none" }}>
          Back to Run Chooser
        </Link>
      </main>
    );
  }

  return (
    <>
      <main style={{ maxWidth: 960, margin: "0 auto", padding: 20 }}>
        <div className="card" style={{ marginBottom: 12 }}>
          <h1 style={{ marginTop: 0, marginBottom: 8 }}>Auto-Follow Series</h1>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}>
            <div style={{ color: "var(--ink-muted)" }}>
              series: <code>{series.seriesId}</code> | ticks: {series.runCount} | latest tick: {series.latestTick} | latest run:{" "}
              <code>{series.latestRunId}</code>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>last_seen_utc: {series.lastSeenUtc ?? "n/a"}</div>
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link href="/" className="btn" style={{ textDecoration: "none" }}>
              Run Chooser
            </Link>
            <Link href={`/run/${encodeURIComponent(activeRunId)}`} className="btn" style={{ textDecoration: "none" }}>
              Open Current Tick
            </Link>
          </div>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))", marginBottom: 12 }}>
          <div className="card">
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Window</div>
            <strong>{recentSummariesDesc.length}/{Math.min(RECENT_WINDOW, series.runCount)} ticks loaded</strong>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>summary fetch {summaryLoading ? "running" : "idle"}</div>
          </div>
          <div className="card">
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Promotion Funnel</div>
            <strong>{majorStats.promotions} promoted / {majorStats.activations} activated</strong>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>in recent window</div>
          </div>
          <div className="card">
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Version Aging</div>
            <strong>v18.{majorStats.versionStart ?? "?"} → v18.{majorStats.versionEnd ?? "?"}</strong>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
              delta: {majorStats.versionDelta === null ? "n/a" : `+${majorStats.versionDelta}`}
            </div>
          </div>
          <div className="card">
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Best Improvement</div>
            <strong>{majorStats.bestMetric ? `${majorStats.bestMetric}` : "n/a"}</strong>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>ratio: {formatRatio(majorStats.bestRatio)}</div>
          </div>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "1fr 1.4fr", marginBottom: 12 }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Campaign Mix</h3>
            {campaignMix.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No summaries yet.</p>}
            {campaignMix.length > 0 && (
              <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
                {campaignMix.slice(0, 8).map((row) => (
                  <li key={row.campaignId}>
                    <code>{row.campaignId}</code>: {row.count}
                  </li>
                ))}
              </ul>
            )}
            <p style={{ marginBottom: 0, color: "var(--ink-muted)", fontSize: 12 }}>escalated ticks: {majorStats.escalatedTicks}</p>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Recent Tick Timeline</h3>
            {recentSummariesAsc.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No timeline rows yet.</p>}
            {recentSummariesAsc.length > 0 && (
              <div className="card" style={{ maxHeight: 300, overflow: "auto", padding: 0 }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>tick</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>action</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>metric</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>esc</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>v18.minor</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>promote/activate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentSummariesAsc.slice(-20).map((row) => (
                      <tr key={row.runId}>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.tick}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.actionKind}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>
                          <code>{row.selectedMetricId ?? "n/a"}</code>
                        </td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>
                          <code>{row.campaignId ?? "n/a"}</code>
                        </td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.escalationLevel}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.versionMinor ?? "n/a"}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>
                          {row.promotionStatus ?? "n/a"} / {row.activationPass ? "PASS" : "FAIL"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>
      <OmegaDashboard key={activeRunId} runId={activeRunId} />
      {(error || summaryError) && (
        <main style={{ maxWidth: 960, margin: "0 auto", padding: "0 20px 20px" }}>
          <div className="card" style={{ color: "var(--danger)" }}>
            refresh error: {error ?? summaryError}
          </div>
        </main>
      )}
    </>
  );
}
