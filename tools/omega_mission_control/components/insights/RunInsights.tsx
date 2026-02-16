"use client";

import { useMemo } from "react";

type RunInsightsProps = {
  snapshot: any;
  dispatches: Array<Record<string, any>>;
};

type ObjectiveRow = {
  metricId: string;
  direction: "MINIMIZE" | "MAXIMIZE";
  current: number | null;
  target: number | null;
  best: number | null;
  weightedGap: number;
  stallTicks: number;
  escalationLevel: number;
  tightenRound: number;
  lastImproveTick: number;
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

function formatQ32(value: number | null, digits = 6): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return value.toFixed(digits);
}

function formatInt(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return String(Math.floor(value));
}

function envMap(value: unknown): Record<string, string> {
  const rec = asRecord(value);
  if (!rec) {
    return {};
  }
  const out: Record<string, string> = {};
  for (const [key, row] of Object.entries(rec)) {
    if (typeof row === "string") {
      out[key] = row;
    }
  }
  return out;
}

function stableEnv(env: Record<string, string>): string {
  return JSON.stringify(Object.keys(env).sort().map((key) => [key, env[key]]));
}

export default function RunInsights({ snapshot, dispatches }: RunInsightsProps) {
  const observation = asRecord(snapshot?.artifacts?.omega_observation_report_v1);
  const decision = asRecord(snapshot?.artifacts?.omega_decision_plan_v1);
  const dispatch = asRecord(snapshot?.artifacts?.omega_dispatch_receipt_v1);
  const runawayState = asRecord(snapshot?.artifacts?.omega_runaway_state_v1);
  const objectives = asRecord(snapshot?.config?.omega_objectives_v1);
  const runawayConfig = asRecord(snapshot?.config?.omega_runaway_config_v1);

  const objectiveRows = useMemo<ObjectiveRow[]>(() => {
    const objectiveMetrics = Array.isArray(objectives?.metrics) ? objectives.metrics : [];
    const metricStates = asRecord(runawayState?.metric_states);
    const observedMetrics = asRecord(observation?.metrics);

    const rows: ObjectiveRow[] = [];
    for (const metricRaw of objectiveMetrics) {
      const metric = asRecord(metricRaw);
      if (!metric) {
        continue;
      }
      const metricId = asString(metric.metric_id);
      if (!metricId) {
        continue;
      }
      const direction: "MINIMIZE" | "MAXIMIZE" = metric.direction === "MAXIMIZE" ? "MAXIMIZE" : "MINIMIZE";
      const state = asRecord(metricStates?.[metricId]);
      const current = q32ToNumber(state?.last_value_q32) ?? q32ToNumber(observedMetrics?.[metricId]);
      const target = q32ToNumber(state?.current_target_q32) ?? q32ToNumber(metric.target_q32);
      const best = q32ToNumber(state?.best_value_q32) ?? current;
      const weight = q32ToNumber(metric.weight_q32) ?? 0;

      let gap = 0;
      if (current !== null && target !== null) {
        gap = direction === "MINIMIZE" ? Math.max(0, current - target) : Math.max(0, target - current);
      }

      rows.push({
        metricId,
        direction,
        current,
        target,
        best,
        weightedGap: gap * weight,
        stallTicks: Math.floor(asNumber(state?.stall_ticks_u64) ?? 0),
        escalationLevel: Math.floor(asNumber(state?.escalation_level_u64) ?? 0),
        tightenRound: Math.floor(asNumber(state?.tighten_round_u64) ?? 0),
        lastImproveTick: Math.floor(asNumber(state?.last_improve_tick_u64) ?? 0),
      });
    }
    return rows.sort((a, b) => b.weightedGap - a.weightedGap || a.metricId.localeCompare(b.metricId));
  }, [objectives, observation, runawayState]);

  const topPressure = objectiveRows.length > 0 ? objectiveRows[0] : null;

  const routeRows = useMemo<Array<{ level: number; campaignId: string }>>(() => {
    const selectedMetric = asString(decision?.runaway_selected_metric_id);
    const routesRoot = asRecord(runawayConfig?.per_metric_route_table);
    if (!selectedMetric || !routesRoot) {
      return [];
    }
    const rows = Array.isArray(routesRoot[selectedMetric]) ? (routesRoot[selectedMetric] as unknown[]) : [];
    const out: Array<{ level: number; campaignId: string }> = [];
    for (const rowRaw of rows) {
      const row = asRecord(rowRaw);
      if (!row) {
        continue;
      }
      const campaignId = asString(row.campaign_id);
      if (!campaignId) {
        continue;
      }
      const level = Math.floor(asNumber(row.level_u64) ?? 0);
      out.push({ level, campaignId });
    }
    return out.sort((a, b) => a.level - b.level || a.campaignId.localeCompare(b.campaignId));
  }, [decision, runawayConfig]);

  const intensityLevel = useMemo(() => {
    const campaignId = asString(decision?.campaign_id);
    const levels = asRecord(runawayState?.campaign_intensity_levels);
    if (!campaignId || !levels) {
      return null;
    }
    return Math.floor(asNumber(levels[campaignId]) ?? 0);
  }, [decision, runawayState]);

  const expectedEnvOverrides = useMemo(() => {
    const campaignId = asString(decision?.campaign_id);
    const level = intensityLevel;
    const table = asRecord(runawayConfig?.per_campaign_intensity_table);
    if (!campaignId || level === null || !table) {
      return {};
    }
    const rows = Array.isArray(table[campaignId]) ? (table[campaignId] as unknown[]) : [];
    for (const rowRaw of rows) {
      const row = asRecord(rowRaw);
      if (!row) {
        continue;
      }
      if (Math.floor(asNumber(row.level_u64) ?? -1) !== level) {
        continue;
      }
      return envMap(row.env_overrides);
    }
    return {};
  }, [decision, intensityLevel, runawayConfig]);

  const decisionEnv = envMap(decision?.runaway_env_overrides);
  const dispatchEnv = envMap(asRecord(dispatch?.invocation)?.env_overrides);

  const envParity = {
    decision_vs_dispatch: stableEnv(decisionEnv) === stableEnv(dispatchEnv),
    expected_vs_dispatch: stableEnv(expectedEnvOverrides) === stableEnv(dispatchEnv),
  };

  const campaignStats = useMemo(() => {
    const map = new Map<
      string,
      {
        dispatches: number;
        promoted: number;
        activated: number;
        invalid: number;
        rollbacks: number;
        latestTick: number;
      }
    >();

    for (const row of dispatches) {
      const campaignId = asString(row.campaign_id) ?? "unknown";
      const existing = map.get(campaignId) ?? {
        dispatches: 0,
        promoted: 0,
        activated: 0,
        invalid: 0,
        rollbacks: 0,
        latestTick: 0,
      };
      existing.dispatches += 1;
      if (asString(row.promotion_status) === "PROMOTED") {
        existing.promoted += 1;
      }
      if (row.activation_pass === true) {
        existing.activated += 1;
      }
      if (asString(row.subverifier_status) === "INVALID") {
        existing.invalid += 1;
      }
      if (asString(row.rollback_cause)) {
        existing.rollbacks += 1;
      }
      existing.latestTick = Math.max(existing.latestTick, Math.floor(asNumber(row.tick_u64) ?? 0));
      map.set(campaignId, existing);
    }

    return Array.from(map.entries())
      .map(([campaignId, row]) => ({ campaignId, ...row }))
      .sort((a, b) => b.dispatches - a.dispatches || b.latestTick - a.latestTick || a.campaignId.localeCompare(b.campaignId));
  }, [dispatches]);

  const deadlockSignal = (() => {
    const actionKind = asString(decision?.action_kind) ?? "NOOP";
    return actionKind === "NOOP" && (topPressure?.weightedGap ?? 0) > 0;
  })();

  return (
    <div className="grid" style={{ gridTemplateColumns: "1.1fr 1fr" }}>
      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Objective Pressure</h3>
          {!runawayState && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>Runaway state artifact not present.</p>}
          {runawayState && objectiveRows.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No objective rows found.</p>}
          {runawayState && objectiveRows.length > 0 && (
            <>
              <p style={{ marginTop: 0 }}>
                top metric: <code>{topPressure?.metricId ?? "n/a"}</code> | weighted_gap={formatQ32(topPressure?.weightedGap ?? null, 6)}
              </p>
              <div className="card" style={{ maxHeight: 360, overflow: "auto", padding: 0 }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>metric</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>current</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>target</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>best</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>weighted_gap</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>stall/escalate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {objectiveRows.map((row) => (
                      <tr key={row.metricId}>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>
                          <code>{row.metricId}</code>
                        </td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(row.current)}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(row.target)}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(row.best)}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>{formatQ32(row.weightedGap, 6)}</td>
                        <td style={{ padding: "6px 10px", fontSize: 12 }}>
                          {row.stallTicks}/{row.escalationLevel} (tighten {row.tightenRound}, last+ {row.lastImproveTick})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Decision + Escalation</h3>
          <p style={{ marginTop: 0 }}>
            action=<code>{asString(decision?.action_kind) ?? "n/a"}</code> | selected_metric=
            <code>{asString(decision?.runaway_selected_metric_id) ?? "n/a"}</code> | campaign=
            <code>{asString(decision?.campaign_id) ?? "n/a"}</code> | escalation=
            <code>{formatInt(asNumber(decision?.runaway_escalation_level_u64))}</code> | intensity=
            <code>{formatInt(intensityLevel)}</code>
          </p>
          {deadlockSignal && (
            <p style={{ color: "var(--danger)", marginTop: 0 }}>
              signal: `NOOP` selected while objective pressure is still positive.
            </p>
          )}
          {routeRows.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No route table entry for selected metric.</p>}
          {routeRows.length > 0 && (
            <div className="card" style={{ maxHeight: 260, overflow: "auto", padding: 0 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>level</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                  </tr>
                </thead>
                <tbody>
                  {routeRows.map((row) => (
                    <tr key={`${row.level}_${row.campaignId}`} style={{ background: row.level === intensityLevel ? "#e8fff8" : "transparent" }}>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.level}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{row.campaignId}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Env Override Determinism</h3>
          <p style={{ marginTop: 0, marginBottom: 8 }}>
            decision_vs_dispatch:{" "}
            <strong style={{ color: envParity.decision_vs_dispatch ? "var(--ok)" : "var(--danger)" }}>
              {envParity.decision_vs_dispatch ? "match" : "mismatch"}
            </strong>
            {" | "}
            expected_vs_dispatch:{" "}
            <strong style={{ color: envParity.expected_vs_dispatch ? "var(--ok)" : "var(--danger)" }}>
              {envParity.expected_vs_dispatch ? "match" : "mismatch"}
            </strong>
          </p>
          <pre style={{ marginTop: 0 }}>
{`expected: ${JSON.stringify(expectedEnvOverrides, null, 2)}
decision: ${JSON.stringify(decisionEnv, null, 2)}
dispatch: ${JSON.stringify(dispatchEnv, null, 2)}`}
          </pre>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Campaign Outcome Matrix</h3>
          {campaignStats.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No dispatches yet.</p>}
          {campaignStats.length > 0 && (
            <div className="card" style={{ maxHeight: 320, overflow: "auto", padding: 0 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>dispatches</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>promoted</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>activated</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>invalid</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>rollbacks</th>
                  </tr>
                </thead>
                <tbody>
                  {campaignStats.map((row) => (
                    <tr key={row.campaignId}>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>
                        <code>{row.campaignId}</code>
                      </td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.dispatches}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.promoted}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.activated}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.invalid}</td>
                      <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.rollbacks}</td>
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
