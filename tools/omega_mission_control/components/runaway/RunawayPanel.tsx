"use client";

type RunawayPanelProps = {
  snapshot: any;
};

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
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function q32ToNumber(value: unknown): number | null {
  const rec = asRecord(value);
  const q = asNumber(rec?.q);
  if (q === null) {
    return null;
  }
  return q / 2 ** 32;
}

function formatQ32(value: number | null): string {
  if (value === null) {
    return "n/a";
  }
  return value.toFixed(6);
}

function envOverrides(value: unknown): Record<string, string> {
  const rec = asRecord(value);
  if (!rec) {
    return {};
  }
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(rec)) {
    if (typeof v === "string") {
      out[k] = v;
    }
  }
  return out;
}

export default function RunawayPanel({ snapshot }: RunawayPanelProps) {
  const decision = asRecord(snapshot?.artifacts?.omega_decision_plan_v1);
  const dispatch = asRecord(snapshot?.artifacts?.omega_dispatch_receipt_v1);
  const runawayState = asRecord(snapshot?.artifacts?.omega_runaway_state_v1);
  const objectives = asRecord(snapshot?.config?.omega_objectives_v1);
  const runawayConfig = asRecord(snapshot?.config?.omega_runaway_config_v1);

  const selectedMetric = asString(decision?.runaway_selected_metric_id);
  const escalationLevel = Math.floor(asNumber(decision?.runaway_escalation_level_u64) ?? 0);
  const versionMinor = asNumber(runawayState?.version_minor_u64);

  const metricStates = asRecord(runawayState?.metric_states);
  const objectiveRows = Array.isArray(objectives?.metrics) ? objectives.metrics : [];

  const routeTableRoot = asRecord(runawayConfig?.per_metric_route_table);
  const routeRowsRaw = selectedMetric ? routeTableRoot?.[selectedMetric] : null;
  const routeRows = Array.isArray(routeRowsRaw)
    ? routeRowsRaw
        .map((row) => asRecord(row))
        .filter((row): row is Record<string, unknown> => row !== null)
        .map((row) => ({
          level_u64: Math.floor(asNumber(row.level_u64) ?? 0),
          campaign_id: asString(row.campaign_id) ?? "n/a",
        }))
        .sort((a, b) => a.level_u64 - b.level_u64 || a.campaign_id.localeCompare(b.campaign_id))
    : [];

  const decisionEnv = envOverrides(decision?.runaway_env_overrides);
  const dispatchEnv = envOverrides(asRecord(dispatch?.invocation)?.env_overrides);

  return (
    <div className="grid" style={{ gridTemplateColumns: "1.15fr 1fr" }}>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Runaway State</h3>
        <p style={{ marginTop: 0, marginBottom: 8 }}>
          version_minor_u64: <strong>{versionMinor ?? "n/a"}</strong>
          {" | "}
          selected_metric: <code>{selectedMetric ?? "n/a"}</code>
          {" | "}
          escalation: <strong>{escalationLevel}</strong>
        </p>

        {objectiveRows.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No objective metrics found.</p>}
        {objectiveRows.length > 0 && (
          <div className="card" style={{ maxHeight: 360, overflow: "auto", padding: 0 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>metric</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>target</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>best</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>last</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>stall</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>esc</th>
                </tr>
              </thead>
              <tbody>
                {objectiveRows.map((metricRaw, idx) => {
                  const metric = asRecord(metricRaw);
                  const metricId = asString(metric?.metric_id) ?? `metric_${idx}`;
                  const state = asRecord(metricStates?.[metricId]);
                  return (
                    <tr key={metricId}>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{metricId}</code>
                      </td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        {formatQ32(q32ToNumber(state?.current_target_q32) ?? q32ToNumber(metric?.target_q32))}
                      </td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(q32ToNumber(state?.best_value_q32))}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(q32ToNumber(state?.last_value_q32))}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{Math.floor(asNumber(state?.stall_ticks_u64) ?? 0)}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{Math.floor(asNumber(state?.escalation_level_u64) ?? 0)}</td>
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
          <h3 style={{ marginTop: 0 }}>Decision / Dispatch Env</h3>
          <p style={{ marginTop: 0, color: "var(--ink-muted)", fontSize: 12 }}>
            selected metric and env overrides must match between decision plan and dispatch receipt.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <strong style={{ fontSize: 12 }}>decision.runaway_env_overrides</strong>
              <pre>{JSON.stringify(decisionEnv, null, 2)}</pre>
            </div>
            <div>
              <strong style={{ fontSize: 12 }}>dispatch.invocation.env_overrides</strong>
              <pre>{JSON.stringify(dispatchEnv, null, 2)}</pre>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Route Ladder</h3>
          {routeRows.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No route ladder for selected metric.</p>}
          {routeRows.length > 0 && (
            <div className="card" style={{ maxHeight: 250, overflow: "auto", padding: 0 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>level</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                  </tr>
                </thead>
                <tbody>
                  {routeRows.map((row) => (
                    <tr key={`${row.level_u64}_${row.campaign_id}`} style={{ background: row.level_u64 === escalationLevel ? "#e8fff8" : "transparent" }}>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.level_u64}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{row.campaign_id}</code>
                      </td>
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
