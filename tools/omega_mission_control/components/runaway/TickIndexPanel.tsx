"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchTextFile, fetchTickIndex } from "../../lib/api";

type TickIndexPanelProps = {
  runId: string;
  selectedTick: number;
  onSelectTick: (tick: number) => void;
};

type LogTab = "dispatch_stdout" | "dispatch_stderr" | "verifier_stdout" | "verifier_stderr";

type TickRow = {
  tick_u64: number;
  action_kind: string | null;
  campaign_id: string | null;
  capability_id: string | null;
  subverifier_status: string | null;
  subverifier_reason_code: string | null;
  promotion_status: string | null;
  promotion_reason_code: string | null;
  activation_success: boolean | null;
  failing_stage: string;
  reason_code: string | null;
  suggested_next_action: string | null;
  dispatch_id: string | null;
  member_run_id: string | null;
  stdout_rel: string | null;
  stderr_rel: string | null;
  verifier_stdout_rel: string | null;
  verifier_stderr_rel: string | null;
};

function asRows(value: Array<Record<string, unknown>>): TickRow[] {
  return value
    .map((row) => {
      const tick = typeof row.tick_u64 === "number" ? Math.floor(row.tick_u64) : null;
      if (tick === null || !Number.isFinite(tick)) {
        return null;
      }
      return {
        tick_u64: tick,
        action_kind: typeof row.action_kind === "string" ? row.action_kind : null,
        campaign_id: typeof row.campaign_id === "string" ? row.campaign_id : null,
        capability_id: typeof row.capability_id === "string" ? row.capability_id : null,
        subverifier_status: typeof row.subverifier_status === "string" ? row.subverifier_status : null,
        subverifier_reason_code: typeof row.subverifier_reason_code === "string" ? row.subverifier_reason_code : null,
        promotion_status: typeof row.promotion_status === "string" ? row.promotion_status : null,
        promotion_reason_code: typeof row.promotion_reason_code === "string" ? row.promotion_reason_code : null,
        activation_success: typeof row.activation_success === "boolean" ? row.activation_success : null,
        failing_stage: typeof row.failing_stage === "string" ? row.failing_stage : "UNKNOWN",
        reason_code: typeof row.reason_code === "string" ? row.reason_code : null,
        suggested_next_action: typeof row.suggested_next_action === "string" ? row.suggested_next_action : null,
        dispatch_id: typeof row.dispatch_id === "string" ? row.dispatch_id : null,
        member_run_id: typeof row.member_run_id === "string" ? row.member_run_id : null,
        stdout_rel: typeof row.stdout_rel === "string" ? row.stdout_rel : null,
        stderr_rel: typeof row.stderr_rel === "string" ? row.stderr_rel : null,
        verifier_stdout_rel: typeof row.verifier_stdout_rel === "string" ? row.verifier_stdout_rel : null,
        verifier_stderr_rel: typeof row.verifier_stderr_rel === "string" ? row.verifier_stderr_rel : null,
      };
    })
    .filter((row): row is TickRow => row !== null)
    .sort((a, b) => b.tick_u64 - a.tick_u64);
}

function rowKey(row: TickRow): string {
  return `${row.tick_u64}:${row.member_run_id ?? "single"}`;
}

export default function TickIndexPanel({ runId, selectedTick, onSelectTick }: TickIndexPanelProps) {
  const [rows, setRows] = useState<TickRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [logTab, setLogTab] = useState<LogTab>("dispatch_stdout");
  const [logText, setLogText] = useState<string>("");
  const [logLoading, setLogLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const payload = await fetchTickIndex(runId);
        if (!active) {
          return;
        }
        const nextRows = asRows(payload.rows);
        setRows(nextRows);
        setError(null);
        if (nextRows.length > 0) {
          setOpenKey((prev) => prev ?? rowKey(nextRows[0]));
        }
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "failed to load tick index");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [runId]);

  const openRow = useMemo(() => rows.find((row) => rowKey(row) === openKey) ?? null, [rows, openKey]);

  useEffect(() => {
    let active = true;
    const loadLog = async () => {
      if (!openRow) {
        setLogText("");
        return;
      }
      const rel =
        logTab === "dispatch_stdout"
          ? openRow.stdout_rel
          : logTab === "dispatch_stderr"
            ? openRow.stderr_rel
            : logTab === "verifier_stdout"
              ? openRow.verifier_stdout_rel
              : openRow.verifier_stderr_rel;
      if (!rel) {
        setLogText("(no file)");
        return;
      }
      setLogLoading(true);
      try {
        const next = await fetchTextFile(runId, rel, openRow.tick_u64);
        if (active) {
          setLogText(next);
        }
      } catch (err) {
        if (active) {
          setLogText(err instanceof Error ? err.message : "failed to load file");
        }
      } finally {
        if (active) {
          setLogLoading(false);
        }
      }
    };
    void loadLog();
    return () => {
      active = false;
    };
  }, [openRow, logTab, runId]);

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1.2fr" }}>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Tick Index</h3>
        {loading && <p>Loading tick index...</p>}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
        {!loading && rows.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No tick rows found.</p>}
        {rows.length > 0 && (
          <div className="card" style={{ maxHeight: 450, overflow: "auto", padding: 0 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>tick</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>stage</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>reason</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isOpen = openKey === rowKey(row);
                  const isFail = row.failing_stage !== "OK";
                  const isSelectedTick = selectedTick === row.tick_u64;
                  return (
                    <tr
                      key={rowKey(row)}
                      onClick={() => {
                        setOpenKey(rowKey(row));
                        onSelectTick(row.tick_u64);
                      }}
                      style={{ cursor: "pointer", background: isOpen ? "#e4ecff" : isSelectedTick ? "#f6f8ff" : "transparent" }}
                    >
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.tick_u64}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <span style={{ color: isFail ? "var(--danger)" : "var(--ok)", fontWeight: 700 }}>{isFail ? "FAIL" : "OK"}</span>
                        {" / "}
                        {row.failing_stage}
                      </td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{row.reason_code ?? "n/a"}</code>
                      </td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{row.campaign_id ?? "n/a"}</code>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Tick Detail</h3>
          {!openRow && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>Select a row to inspect.</p>}
          {openRow && (
            <>
              <p style={{ marginTop: 0 }}>
                tick <strong>{openRow.tick_u64}</strong>
                {" | "}
                action <code>{openRow.action_kind ?? "n/a"}</code>
                {" | "}
                dispatch <code>{openRow.dispatch_id ?? "n/a"}</code>
              </p>
              <p style={{ marginTop: 0 }}>
                subverifier: <strong>{openRow.subverifier_status ?? "n/a"}</strong>
                {" | "}
                promotion: <strong>{openRow.promotion_status ?? "n/a"}</strong>
                {" | "}
                activation: <strong>{openRow.activation_success === null ? "n/a" : openRow.activation_success ? "PASS" : "FAIL"}</strong>
              </p>
              <p style={{ marginBottom: 0 }}>
                suggested_next_action: <code>{openRow.suggested_next_action ?? "n/a"}</code>
              </p>
            </>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Log Quick-Open</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {([
              ["dispatch_stdout", "Dispatch stdout"],
              ["dispatch_stderr", "Dispatch stderr"],
              ["verifier_stdout", "Verifier stdout"],
              ["verifier_stderr", "Verifier stderr"],
            ] as const).map(([tab, label]) => (
              <button
                key={tab}
                type="button"
                className="btn"
                onClick={() => setLogTab(tab)}
                style={{ background: logTab === tab ? "#e4ecff" : undefined }}
              >
                {label}
              </button>
            ))}
          </div>
          {logLoading && <p>Loading log...</p>}
          <pre>{logText || "(empty)"}</pre>
        </div>
      </section>
    </div>
  );
}
