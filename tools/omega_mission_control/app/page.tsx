"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchRuns } from "../lib/api";
import type { RunInfo } from "../lib/types_v18";

function sortByLastSeenDesc(rows: RunInfo[]): RunInfo[] {
  return [...rows].sort((a, b) => {
    const aSeen = a.last_seen_utc ?? "";
    const bSeen = b.last_seen_utc ?? "";
    if (aSeen !== bSeen) {
      return bSeen.localeCompare(aSeen);
    }
    return a.run_id.localeCompare(b.run_id);
  });
}

export default function RunChooserPage() {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRawTicks, setShowRawTicks] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetchRuns(showRawTicks);
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
  }, [showRawTicks]);

  const seriesRuns = useMemo(() => sortByLastSeenDesc(runs.filter((row) => row.kind === "series")), [runs]);
  const singleRuns = useMemo(() => sortByLastSeenDesc(runs.filter((row) => row.kind === "single")), [runs]);

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 20 }}>
      <div className="card" style={{ marginBottom: 14 }}>
        <h1 style={{ marginTop: 0 }}>Omega Mission Control v18.1</h1>
        <p style={{ margin: 0, color: "var(--ink-muted)" }}>
          Series-aware run chooser. Tick directories are grouped into one operational run by default.
        </p>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>Run Chooser</h2>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={showRawTicks}
              onChange={(e) => setShowRawTicks(e.target.checked)}
            />
            Show raw tick runs
          </label>
        </div>

        {loading && <p>Loading runs...</p>}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
        {!loading && runs.length === 0 && <p>No Omega v18 runs detected yet.</p>}

        {seriesRuns.length > 0 && (
          <>
            <h3>Series Runs</h3>
            <div className="grid">
              {seriesRuns.map((run) => (
                <Link
                  key={run.run_id}
                  href={`/run/${encodeURIComponent(run.run_id)}`}
                  className="card"
                  style={{ textDecoration: "none", display: "block" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                    <strong>{run.run_id}</strong>
                    <span
                      style={{
                        fontSize: 12,
                        border: "1px solid var(--line)",
                        borderRadius: 999,
                        padding: "2px 8px",
                        background: run.mode === "mock" ? "var(--accent-soft)" : "#eef2ff",
                      }}
                    >
                      {run.mode}
                    </span>
                  </div>
                  <p style={{ marginBottom: 0, color: "var(--ink-muted)", fontSize: 13 }}>
                    ticks: {run.tick_count ?? "n/a"} | min: {run.tick_min_u64 ?? "n/a"} | max: {run.tick_max_u64 ?? "n/a"}
                  </p>
                  <p style={{ marginBottom: 0, color: "var(--ink-muted)", fontSize: 13 }}>
                    last_seen_utc: {run.last_seen_utc ?? "n/a"}
                  </p>
                </Link>
              ))}
            </div>
          </>
        )}

        <h3>Single Runs</h3>
        {singleRuns.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No standalone runs in current view.</p>}
        <div className="grid">
          {singleRuns.map((run) => (
            <Link
              key={run.run_id}
              href={`/run/${encodeURIComponent(run.run_id)}`}
              className="card"
              style={{ textDecoration: "none", display: "block" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                <strong>{run.run_id}</strong>
                <span
                  style={{
                    fontSize: 12,
                    border: "1px solid var(--line)",
                    borderRadius: 999,
                    padding: "2px 8px",
                    background: run.mode === "mock" ? "var(--accent-soft)" : "#eef2ff",
                  }}
                >
                  {run.mode}
                </span>
              </div>
              <p style={{ marginBottom: 0, color: "var(--ink-muted)", fontSize: 13 }}>
                last_seen_utc: {run.last_seen_utc ?? "n/a"}
              </p>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
