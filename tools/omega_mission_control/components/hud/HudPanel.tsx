"use client";

import { formatPercent, q32Percent } from "../../lib/q32";
import type { OmegaMode } from "../../lib/types_v18";

type HudPanelProps = {
  mode: OmegaMode;
  snapshot: any;
  dispatches: Array<Record<string, any>>;
  ledgerEvents: Array<Record<string, any>>;
  nowUtc: string;
};

type Gauge = {
  label: string;
  current: number;
  max: number;
  unit: string;
};

function gaugePercent(g: Gauge): number {
  if (!Number.isFinite(g.max) || g.max <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (g.current / g.max) * 100));
}

export default function HudPanel({ mode, snapshot, dispatches, ledgerEvents, nowUtc }: HudPanelProps) {
  const latestSnapshot = snapshot?.latest_snapshot ?? null;
  const state = snapshot?.artifacts?.omega_state_v1 ?? null;
  const decision = snapshot?.artifacts?.omega_decision_plan_v1 ?? null;
  const issueBundle = snapshot?.artifacts?.omega_issue_bundle_v1 ?? null;
  const subverifier = snapshot?.artifacts?.omega_subverifier_receipt_v1 ?? null;
  const budgets = snapshot?.config?.omega_budgets_v1 ?? null;
  const runArtifacts = snapshot?.run_artifacts ?? null;
  const preflight = runArtifacts?.omega_preflight_report_v1 ?? null;
  const gateProof = runArtifacts?.omega_gate_proof_v1 ?? null;
  const diagnostic = runArtifacts?.omega_diagnostic_packet_v1 ?? null;
  const replayManifest = runArtifacts?.omega_replay_manifest_v1 ?? null;
  const llmRouterPlan = snapshot?.llm_router_plan_v1 ?? null;
  const llmToolTrace = Array.isArray(snapshot?.llm_tool_trace_v1) ? snapshot.llm_tool_trace_v1 : [];

  const tick = latestSnapshot?.tick_u64 ?? state?.tick_u64 ?? 0;
  const lastEvent = ledgerEvents[ledgerEvents.length - 1] ?? null;
  const hasSafeHaltEvent = ledgerEvents.some((e) => e.event_type === "SAFE_HALT");
  const actionKind = decision?.action_kind ?? "NOOP";

  let activeMode = "Sleeping";
  if (hasSafeHaltEvent || actionKind === "SAFE_HALT") {
    activeMode = "SAFE_HALT";
  } else if (actionKind === "RUN_CAMPAIGN" || actionKind === "RUN_GOAL_TASK") {
    activeMode = "Optimizing";
  } else if (lastEvent?.event_type === "OBSERVATION" || lastEvent?.event_type === "ISSUE") {
    activeMode = "Diagnosing";
  }

  const budgetRemaining = latestSnapshot?.budget_remaining ?? state?.budget_remaining ?? {};
  const gauges: Gauge[] = [
    {
      label: "CPU",
      current: q32Percent(budgetRemaining?.cpu_cost_q32),
      max: q32Percent(budgets?.max_cpu_cost_q32_per_day),
      unit: "%",
    },
    {
      label: "Build",
      current: q32Percent(budgetRemaining?.build_cost_q32),
      max: q32Percent(budgets?.max_build_cost_q32_per_day),
      unit: "%",
    },
    {
      label: "Verifier",
      current: q32Percent(budgetRemaining?.verifier_cost_q32),
      max: q32Percent(budgets?.max_verifier_cost_q32_per_day),
      unit: "%",
    },
    {
      label: "Disk",
      current: Number(budgetRemaining?.disk_bytes_u64 ?? 0),
      max: Number(budgets?.max_disk_bytes_per_day ?? 1),
      unit: "bytes",
    },
  ];

  const anyLowBudget = gauges.some((g) => gaugePercent(g) < 20);
  const hasIssues = Array.isArray(issueBundle?.issues) && issueBundle.issues.length > 0;
  const hasInvalidSubVerifier = subverifier?.result?.status === "INVALID";

  let safety = "Green";
  let safetyColor = "var(--ok)";
  if (hasSafeHaltEvent || actionKind === "SAFE_HALT" || hasInvalidSubVerifier) {
    safety = "Red";
    safetyColor = "var(--danger)";
  } else if (hasIssues || anyLowBudget) {
    safety = "Amber";
    safetyColor = "var(--warn)";
  }

  const heatTiles = Array.from({ length: 14 }, (_, i) => {
    const d = dispatches[i % Math.max(1, dispatches.length)];
    return {
      core: i + 1,
      campaign: d?.campaign_id ?? "idle",
      busy: !!d,
    };
  });

  return (
    <div className="grid" style={{ gridTemplateColumns: "1.4fr 1fr", alignItems: "start" }}>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Global System Status</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 10 }}>
          <div className="card" style={{ padding: 10 }}>
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Heartbeat</div>
            <strong>tick {tick}</strong>
            <div style={{ fontSize: 12 }}>{nowUtc}</div>
          </div>
          <div className="card" style={{ padding: 10 }}>
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Mode</div>
            <strong>{activeMode}</strong>
            <div style={{ fontSize: 12 }}>{lastEvent?.event_type ?? "n/a"}</div>
          </div>
          <div className="card" style={{ padding: 10 }}>
            <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>Safety</div>
            <strong style={{ color: safetyColor }}>{safety}</strong>
            <div style={{ fontSize: 12 }}>{hasInvalidSubVerifier ? "INVALID subverifier" : hasIssues ? "issues present" : "nominal"}</div>
          </div>
        </div>

        <h4>Budget Gauges</h4>
        <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))" }}>
          {gauges.map((g) => {
            const percent = gaugePercent(g);
            return (
              <div className="card" key={g.label} style={{ padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>{g.label}</strong>
                  <span>{formatPercent(percent)}</span>
                </div>
                <div style={{ height: 8, background: "#e8edf6", borderRadius: 999, overflow: "hidden", marginTop: 8 }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${percent}%`,
                      background: percent < 20 ? "var(--danger)" : percent < 40 ? "var(--warn)" : "var(--accent)",
                    }}
                  />
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-muted)" }}>
                  {g.current.toFixed(2)} / {g.max.toFixed(2)} {g.unit}
                </div>
              </div>
            );
          })}
        </div>

        <h4>Run Artifacts</h4>
        <div className="card" style={{ padding: 10 }}>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            preflight {preflight ? (preflight.ok_b ? "PASS" : "FAIL") : "n/a"} | gate proof {gateProof ? "present" : "missing"}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            diagnostic {diagnostic ? "present" : "missing"} | replay manifest {replayManifest ? "present" : "missing"}
          </div>
        </div>

        <h4>LLM Router</h4>
        <div className="card" style={{ padding: 10 }}>
          {llmRouterPlan ? (
            <>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                tick={String(llmRouterPlan.created_from_tick_u64 ?? "n/a")} trace_rows={llmToolTrace.length}
              </div>
              <div style={{ fontSize: 12 }}>
                web_queries={Array.isArray(llmRouterPlan.web_queries) ? llmRouterPlan.web_queries.length : 0} goal_injections=
                {Array.isArray(llmRouterPlan.goal_injections) ? llmRouterPlan.goal_injections.length : 0}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>LLM router artifacts not present.</div>
          )}
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Resource Heatmap</h3>
        {mode === "mock" ? (
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
            {heatTiles.map((tile) => (
              <div
                key={tile.core}
                className="card"
                style={{
                  padding: 8,
                  background: tile.busy ? "var(--accent-soft)" : "#f3f4f8",
                  borderColor: tile.busy ? "#b6e9dd" : "var(--line)",
                }}
              >
                <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>core {tile.core}</div>
                <div style={{ fontSize: 12 }}>{tile.campaign}</div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ margin: 0, color: "var(--ink-muted)" }}>
            Telemetry unavailable (no per-core metric in v18.0 artifacts)
          </p>
        )}
      </section>
    </div>
  );
}
