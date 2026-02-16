"use client";

import JSZip from "jszip";
import { useMemo, useState } from "react";
import { canonHash } from "../../lib/canon_sha256";
import { fetchHashSearch, fetchTickCompare } from "../../lib/api";

type ImmutableLedgerProps = {
  runId: string;
  snapshot: any;
  ledgerEvents: Array<Record<string, any>>;
  dispatches: Array<Record<string, any>>;
  currentTick: number;
  onSelectTick: (tick: number) => void;
};

function recomputeTrace(trace: any): { pass: boolean; h0: string; expected: string; computed: string; mismatch: number | null } {
  const h0 = typeof trace?.H0 === "string" ? trace.H0 : "";
  const expected = typeof trace?.H_final === "string" ? trace.H_final : "";
  const hashes: string[] = Array.isArray(trace?.artifact_hashes) ? trace.artifact_hashes : [];

  let head = h0;
  let mismatch: number | null = null;
  hashes.forEach((artifactHash, i) => {
    head = canonHash({ schema_version: "omega_trace_step_v1", prev: head, artifact_hash: artifactHash });
    if (mismatch === null && i === hashes.length - 1 && head !== expected) {
      mismatch = i;
    }
  });

  return {
    pass: !!expected && head === expected,
    h0,
    expected,
    computed: head,
    mismatch,
  };
}

function validateLedger(events: Array<Record<string, any>>): { pass: boolean; firstMismatch: number | null; reason: string | null } {
  let prev: string | null = null;
  for (let i = 0; i < events.length; i += 1) {
    const row = events[i];
    if ((row.prev_event_id ?? null) !== prev) {
      return { pass: false, firstMismatch: i, reason: "prev_event_id mismatch" };
    }
    const recomputed = canonHash({
      schema_version: row.schema_version,
      tick_u64: row.tick_u64,
      event_type: row.event_type,
      artifact_hash: row.artifact_hash,
      prev_event_id: row.prev_event_id ?? null,
    });
    if (recomputed !== row.event_id) {
      return { pass: false, firstMismatch: i, reason: "event_id hash mismatch" };
    }
    prev = row.event_id;
  }
  return { pass: true, firstMismatch: null, reason: null };
}

function trophyRows(dispatches: Array<Record<string, any>>): Array<Record<string, any>> {
  return dispatches.filter((row) => row.promotion_status === "PROMOTED" && row.activation_pass === true);
}

export default function ImmutableLedger({ runId, snapshot, ledgerEvents, dispatches, currentTick, onSelectTick }: ImmutableLedgerProps) {
  const [hashQuery, setHashQuery] = useState("");
  const [hashResult, setHashResult] = useState<any>(null);
  const [tickA, setTickA] = useState<number | null>(null);
  const [tickB, setTickB] = useState<number | null>(null);
  const [compareResult, setCompareResult] = useState<any>(null);

  const trace = snapshot?.artifacts?.omega_trace_hash_chain_v1 ?? null;
  const traceValidation = useMemo(() => recomputeTrace(trace), [trace]);
  const ledgerValidation = useMemo(() => validateLedger(ledgerEvents), [ledgerEvents]);
  const trophies = useMemo(() => trophyRows(dispatches), [dispatches]);

  const ticks: number[] = Array.isArray(snapshot?.ticks) ? snapshot.ticks : [];

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Trace Chain Validator</h3>
          <p style={{ marginTop: 0 }}>H0: <code>{traceValidation.h0 || "n/a"}</code></p>
          <p>H_final (expected): <code>{traceValidation.expected || "n/a"}</code></p>
          <p>H_final (computed): <code>{traceValidation.computed || "n/a"}</code></p>
          <p style={{ color: traceValidation.pass ? "var(--ok)" : "var(--danger)", marginBottom: 0 }}>
            {traceValidation.pass ? "PASS" : `FAIL${traceValidation.mismatch !== null ? ` (first mismatch step ${traceValidation.mismatch})` : ""}`}
          </p>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Ledger Chain Validator</h3>
          <p style={{ marginBottom: 0, color: ledgerValidation.pass ? "var(--ok)" : "var(--danger)" }}>
            {ledgerValidation.pass
              ? `PASS (${ledgerEvents.length} events checked)`
              : `FAIL at line ${ledgerValidation.firstMismatch}: ${ledgerValidation.reason}`}
          </p>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Time Machine</h3>
          {ticks.length === 0 ? (
            <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No snapshot ticks available.</p>
          ) : (
            <>
              <input
                type="range"
                min={ticks[0]}
                max={ticks[ticks.length - 1]}
                value={currentTick || ticks[ticks.length - 1]}
                onChange={(e) => onSelectTick(Number(e.target.value))}
              />
              <p style={{ marginBottom: 0 }}>
                Selected tick: <strong>{currentTick}</strong>
              </p>
            </>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Global Hash Search</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={hashQuery} onChange={(e) => setHashQuery(e.target.value)} placeholder="sha256:<hex>" />
            <button
              className="btn"
              type="button"
              onClick={async () => {
                const res = await fetchHashSearch(runId, hashQuery.trim());
                setHashResult(res);
              }}
            >
              Search
            </button>
          </div>
          <pre>{JSON.stringify(hashResult ?? { matches: [] }, null, 2)}</pre>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Compare Ticks</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8 }}>
            <select value={tickA ?? ""} onChange={(e) => setTickA(Number(e.target.value))}>
              <option value="">tick A</option>
              {ticks.map((tick) => (
                <option key={`a_${tick}`} value={tick}>{tick}</option>
              ))}
            </select>
            <select value={tickB ?? ""} onChange={(e) => setTickB(Number(e.target.value))}>
              <option value="">tick B</option>
              {ticks.map((tick) => (
                <option key={`b_${tick}`} value={tick}>{tick}</option>
              ))}
            </select>
            <button
              className="btn"
              type="button"
              disabled={tickA === null || tickB === null}
              onClick={async () => {
                if (tickA === null || tickB === null) {
                  return;
                }
                const res = await fetchTickCompare(runId, tickA, tickB);
                setCompareResult(res);
              }}
            >
              Compare
            </button>
          </div>
          <pre>{JSON.stringify(compareResult ?? {}, null, 2)}</pre>
        </div>

        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <h3 style={{ marginTop: 0, marginBottom: 0 }}>Trophy Case</h3>
            <button
              className="btn primary"
              type="button"
              disabled={trophies.length === 0}
              onClick={async () => {
                const zip = new JSZip();
                const json = {
                  run_id: runId,
                  trophies,
                };
                const texLines = [
                  "\\section*{Omega Trophy Case}",
                  `Total trophies: ${trophies.length}\\\\`,
                  "\\begin{itemize}",
                  ...trophies.map(
                    (t) =>
                      `\\item tick ${t.tick_u64} campaign ${t.campaign_id} before ${t.activation_receipt?.before_active_manifest_hash ?? "n/a"} after ${t.activation_receipt?.after_active_manifest_hash ?? "n/a"}`,
                  ),
                  "\\end{itemize}",
                ];
                zip.file("trophies.json", JSON.stringify(json, null, 2));
                zip.file("trophies.tex", texLines.join("\n"));
                trophies.forEach((row, i) => {
                  zip.file(`receipts/trophy_${i + 1}_dispatch.json`, JSON.stringify(row.dispatch_receipt ?? {}, null, 2));
                  zip.file(`receipts/trophy_${i + 1}_promotion.json`, JSON.stringify(row.promotion_receipt ?? {}, null, 2));
                  zip.file(`receipts/trophy_${i + 1}_activation.json`, JSON.stringify(row.activation_receipt ?? {}, null, 2));
                });
                const blob = await zip.generateAsync({ type: "blob" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `omega_trophy_case_${runId}.zip`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Export Trophy Case
            </button>
          </div>
          {trophies.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No promotions with successful activation yet.</p>}
          {trophies.length > 0 && (
            <div className="card" style={{ maxHeight: 360, overflow: "auto", padding: 0 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>tick</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>before</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>after</th>
                  </tr>
                </thead>
                <tbody>
                  {trophies.map((row) => (
                    <tr key={`${row.dispatch_id}_${row.tick_u64}`}>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.tick_u64}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.campaign_id}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.activation_receipt?.before_active_manifest_hash ?? "n/a"}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.activation_receipt?.after_active_manifest_hash ?? "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
