"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchSnapshot } from "../../lib/api";
import type { OmegaMode, WsServerMessage } from "../../lib/types_v18";
import { WS_VERSION } from "../../lib/types_v18";
import CampaignCommander from "../commander/CampaignCommander";
import StrategicDirector from "../director/StrategicDirector";
import HudPanel from "../hud/HudPanel";
import RunInsights from "../insights/RunInsights";
import ImmutableLedger from "../ledger/ImmutableLedger";
import RunawayPanel from "../runaway/RunawayPanel";
import TickIndexPanel from "../runaway/TickIndexPanel";
import BrainView from "../telemetry/BrainView";

type TabKey =
  | "HUD"
  | "Insights"
  | "GE Audit"
  | "Runaway"
  | "Ticks"
  | "Brain View"
  | "Campaign Commander"
  | "Strategic Director"
  | "Immutable Ledger";

const TABS: TabKey[] = [
  "HUD",
  "Insights",
  "GE Audit",
  "Runaway",
  "Ticks",
  "Brain View",
  "Campaign Commander",
  "Strategic Director",
  "Immutable Ledger",
];

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function eventSchema(eventType: string): string {
  if (eventType === "STATE") return "omega_state_v1";
  if (eventType === "OBSERVATION") return "omega_observation_report_v1";
  if (eventType === "ISSUE") return "omega_issue_bundle_v1";
  if (eventType === "DECISION" || eventType === "SAFE_HALT") return "omega_decision_plan_v1";
  if (eventType === "DISPATCH") return "omega_dispatch_receipt_v1";
  if (eventType === "SUBVERIFIER") return "omega_subverifier_receipt_v1";
  if (eventType === "PROMOTION") return "omega_promotion_receipt_v1";
  if (eventType === "ACTIVATION") return "omega_activation_receipt_v1";
  if (eventType === "ROLLBACK") return "omega_rollback_receipt_v1";
  if (eventType === "SNAPSHOT") return "omega_tick_snapshot_v1";
  return "omega_state_v1";
}

async function fetchJson(url: string): Promise<any> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

export default function OmegaDashboard({ runId }: { runId: string }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [tab, setTab] = useState<TabKey>("HUD");
  const [snapshot, setSnapshot] = useState<any>(null);
  const [dispatches, setDispatches] = useState<Array<Record<string, any>>>([]);
  const [ledgerEvents, setLedgerEvents] = useState<Array<Record<string, any>>>([]);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [inspectedArtifact, setInspectedArtifact] = useState<{ schema: string; hash: string; payload: unknown } | null>(null);
  const [paused, setPaused] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsMode, setWsMode] = useState<OmegaMode>("mock");
  const [nowUtc, setNowUtc] = useState(new Date().toISOString());
  const [manualIntervention, setManualIntervention] = useState(false);
  const [localHalted, setLocalHalted] = useState(false);
  const [directiveHistory, setDirectiveHistory] = useState<Array<{ submitted_at_utc: string; path: string }>>([]);
  const [selectedTick, setSelectedTick] = useState<number>(0);

  const refreshSnapshot = useCallback(
    async (tick?: number) => {
      const res = await fetchSnapshot(runId, tick);
      setSnapshot(res.payload);
      if (typeof res.payload?.latest_snapshot?.tick_u64 === "number") {
        setSelectedTick(res.payload.latest_snapshot.tick_u64);
      }
      if (Array.isArray((res.payload as any)?.dispatch_timeline)) {
        setDispatches((res.payload as any).dispatch_timeline as Array<Record<string, any>>);
      }
      if (Array.isArray((res.payload as any)?.ledger_tail)) {
        const rows = ((res.payload as any).ledger_tail as Array<Record<string, any>>).map((row, i) => ({ ...row, __line: i }));
        setLedgerEvents(rows);
      }
    },
    [runId],
  );

  useEffect(() => {
    void refreshSnapshot();
  }, [refreshSnapshot]);

  useEffect(() => {
    const timer = setInterval(() => setNowUtc(new Date().toISOString()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    const pollDispatches = async () => {
      try {
        const res = await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}/dispatches`);
        if (!active) return;
        setDispatches(Array.isArray(res.dispatches) ? res.dispatches : []);
      } catch {
        // ignore
      }
    };
    void pollDispatches();
    const timer = setInterval(() => void pollDispatches(), 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [runId]);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      ws.send(
        JSON.stringify({
          v: WS_VERSION,
          type: "HELLO",
          run_id: runId,
          from_line: 0,
          send_full_snapshot: true,
        }),
      );
    };

    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (ev) => {
      let msg: WsServerMessage | null = null;
      try {
        msg = JSON.parse(ev.data) as WsServerMessage;
      } catch {
        return;
      }

      if (msg.type === "WELCOME") {
        setWsMode(msg.mode);
        return;
      }

      if (msg.type === "FULL_SNAPSHOT") {
        setSnapshot(msg.payload);
        if (typeof msg.payload?.latest_snapshot?.tick_u64 === "number") {
          setSelectedTick(msg.payload.latest_snapshot.tick_u64);
        }
        if (Array.isArray((msg.payload as any)?.dispatch_timeline)) {
          setDispatches((msg.payload as any).dispatch_timeline as Array<Record<string, any>>);
        }
        return;
      }

      if (msg.type === "LEDGER_EVENT") {
        setLedgerEvents((prev) => {
          const next = [...prev, { ...msg.event, __line: msg.line }];
          return next.slice(-1000);
        });
        return;
      }

      if (msg.type === "ARTIFACT") {
        setInspectedArtifact({ schema: msg.schema, hash: msg.hash, payload: msg.payload });
        return;
      }

      if (msg.type === "DIRECTIVE_SUBMITTED") {
        setDirectiveHistory((prev) => [...prev, { submitted_at_utc: msg.submitted_at_utc, path: msg.path }].slice(-50));
        return;
      }

      if (msg.type === "ERROR") {
        // eslint-disable-next-line no-console
        console.error(msg.code, msg.detail);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  useEffect(() => {
    if (!localHalted) {
      return;
    }
    setPaused(true);
    wsRef.current?.send(JSON.stringify({ v: WS_VERSION, type: "SET_PAUSE", paused: true }));
  }, [localHalted]);

  const topTick = snapshot?.latest_snapshot?.tick_u64 ?? 0;
  const topAction = snapshot?.artifacts?.omega_decision_plan_v1?.action_kind ?? "NOOP";
  const geAudit = asRecord(snapshot?.ge_audit_report_v1);
  const geKpi = asRecord(geAudit?.kpi);
  const geNovelty = asRecord(geAudit?.novelty);
  const geFlags = Array.isArray(geAudit?.falsification_flags) ? (geAudit?.falsification_flags as unknown[]) : [];
  const geYieldQ32 = Math.floor(asNumber(geKpi?.yield_promotions_per_wall_ms_q32) ?? 0);
  const geYieldFloat = geYieldQ32 / 2 ** 32;
  const geNoveltyQ32 = Math.floor(asNumber(geNovelty?.novelty_coverage_q32) ?? 0);
  const geNoveltyFloat = geNoveltyQ32 / 2 ** 32;

  return (
    <main style={{ padding: 14 }}>
      <div className="card" style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <div>
          <strong>Omega Mission Control</strong> | run <code>{runId}</code>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            tick {topTick} | action {topAction} | ws {wsConnected ? "connected" : "disconnected"} | mode {wsMode}
          </div>
        </div>
        <div style={{ fontSize: 12 }}>
          {paused ? <span style={{ color: "var(--warn)" }}>Paused (daemon continues)</span> : <span>Live</span>}
        </div>
      </div>

      <div className="layout" style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12 }}>
        <aside className="card" style={{ alignSelf: "start", position: "sticky", top: 12 }}>
          <Link href="/" className="btn" style={{ display: "block", textAlign: "center", marginBottom: 10, textDecoration: "none" }}>
            Run Chooser
          </Link>
          {TABS.map((name) => (
            <button
              key={name}
              type="button"
              className="btn"
              onClick={() => setTab(name)}
              style={{
                width: "100%",
                marginBottom: 8,
                background: tab === name ? "#e4ecff" : undefined,
                textAlign: "left",
              }}
            >
              {name}
            </button>
          ))}
        </aside>

        <section className="grid" style={{ alignItems: "start" }}>
          <HudPanel mode={wsMode} snapshot={snapshot} dispatches={dispatches} ledgerEvents={ledgerEvents} nowUtc={nowUtc} />

          {tab === "HUD" && <div className="card">HUD summary is pinned above.</div>}

          {tab === "Insights" && <RunInsights snapshot={snapshot} dispatches={dispatches} />}

          {tab === "GE Audit" && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>GE Audit</h3>
              {!geAudit ? (
                <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>
                  GE_AUDIT_REPORT_v1.json not found for this run.
                </p>
              ) : (
                <div style={{ display: "grid", gap: 10 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(220px,1fr))", gap: 10 }}>
                    <div className="card">
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Promotions</div>
                      <strong>{Math.floor(asNumber(geKpi?.promote_u64) ?? 0)}</strong>
                    </div>
                    <div className="card">
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Total wall ms</div>
                      <strong>{Math.floor(asNumber(geKpi?.total_wall_ms_u64) ?? 0)}</strong>
                    </div>
                    <div className="card">
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Yield promotions / wall-ms (q32)</div>
                      <strong>{geYieldQ32}</strong>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{geYieldFloat.toFixed(8)} float</div>
                    </div>
                    <div className="card">
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Novelty coverage (q32)</div>
                      <strong>{geNoveltyQ32}</strong>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{geNoveltyFloat.toFixed(6)} float</div>
                    </div>
                  </div>

                  <div className="card">
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 6 }}>Falsification flags</div>
                    {geFlags.length === 0 ? (
                      <strong>None</strong>
                    ) : (
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {geFlags.map((flag, idx) => (
                          <li key={`${idx}-${String(flag)}`}>
                            <code>{String(flag)}</code>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "Runaway" && <RunawayPanel snapshot={snapshot} />}

          {tab === "Ticks" && (
            <TickIndexPanel
              runId={runId}
              selectedTick={selectedTick}
              onSelectTick={(tick) => {
                setSelectedTick(tick);
                void refreshSnapshot(tick);
              }}
            />
          )}

          {tab === "Brain View" && (
            <BrainView
              ledgerEvents={ledgerEvents}
              paused={paused}
              onTogglePause={() => {
                const next = !paused;
                setPaused(next);
                wsRef.current?.send(JSON.stringify({ v: WS_VERSION, type: "SET_PAUSE", paused: next }));
              }}
              selectedLine={selectedLine}
              onSelectLine={(line, event) => {
                setSelectedLine(line);
                const schema = eventSchema(String(event.event_type));
                wsRef.current?.send(
                  JSON.stringify({
                    v: WS_VERSION,
                    type: "REQUEST_ARTIFACT",
                    run_id: runId,
                    schema,
                    hash: event.artifact_hash,
                  }),
                );
              }}
              inspectedArtifact={inspectedArtifact}
              observation={snapshot?.artifacts?.omega_observation_report_v1 ?? null}
            />
          )}

          {tab === "Campaign Commander" && <CampaignCommander runId={runId} dispatches={dispatches} />}

          {tab === "Strategic Director" && (
            <StrategicDirector
              mode={wsMode}
              manualIntervention={manualIntervention}
              setManualIntervention={setManualIntervention}
              halted={localHalted}
              setHalted={setLocalHalted}
              goalQueue={snapshot?.config?.omega_goal_queue_v1 ?? null}
              directiveHistory={directiveHistory}
              tick={topTick}
            />
          )}

          {tab === "Immutable Ledger" && (
            <ImmutableLedger
              runId={runId}
              snapshot={snapshot}
              ledgerEvents={ledgerEvents}
              dispatches={dispatches}
              currentTick={selectedTick}
              onSelectTick={(tick) => {
                setSelectedTick(tick);
                void refreshSnapshot(tick);
              }}
            />
          )}
        </section>
      </div>
    </main>
  );
}
