"use client";

import JsonBlock from "../common/JsonBlock";

type BrainViewProps = {
  ledgerEvents: Array<Record<string, any>>;
  paused: boolean;
  onTogglePause: () => void;
  selectedLine: number | null;
  onSelectLine: (line: number, event: Record<string, any>) => void;
  inspectedArtifact: { schema: string; hash: string; payload: unknown } | null;
  observation: Record<string, any> | null;
};

const NODES = ["STATE", "OBSERVATION", "ISSUE", "DECISION", "DISPATCH", "SUBVERIFIER", "PROMOTION", "ACTIVATION/ROLLBACK", "SNAPSHOT"];

function axisValue(metrics: Record<string, any> | null, key: string): string {
  const row = metrics?.[key];
  if (!row) {
    return "N/A";
  }
  if (typeof row === "object" && typeof row.q === "number") {
    return (row.q / 2 ** 32).toFixed(4);
  }
  if (typeof row === "number") {
    return row.toFixed(4);
  }
  return "N/A";
}

export default function BrainView({ ledgerEvents, paused, onTogglePause, selectedLine, onSelectLine, inspectedArtifact, observation }: BrainViewProps) {
  const latestTypes = new Set(ledgerEvents.slice(-40).map((e) => String(e.event_type)));
  const metrics = (observation?.metrics ?? null) as Record<string, any> | null;

  return (
    <div className="grid" style={{ gridTemplateColumns: "1.2fr 1fr" }}>
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <h3 style={{ marginTop: 0 }}>Live Decision Graph</h3>
          <button className="btn warn" type="button" onClick={onTogglePause}>
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
        {paused && <p style={{ marginTop: -6, color: "var(--warn)" }}>Paused (daemon continues)</p>}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 8 }}>
          {NODES.map((node) => {
            const active = node.includes("/")
              ? latestTypes.has("ACTIVATION") || latestTypes.has("ROLLBACK")
              : latestTypes.has(node);
            return (
              <div
                key={node}
                className="card"
                style={{
                  padding: 10,
                  background: active ? "#e8fff8" : "#f4f6fb",
                  borderColor: active ? "#92e4c8" : "var(--line)",
                  transition: "all 180ms ease",
                }}
              >
                <strong style={{ fontSize: 12 }}>{node}</strong>
              </div>
            );
          })}
        </div>

        <h4>Incoming Ledger Events</h4>
        <div className="card" style={{ maxHeight: 340, overflow: "auto", padding: 0 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>line</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>tick</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>type</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>hash</th>
              </tr>
            </thead>
            <tbody>
              {ledgerEvents.slice(-200).map((event, idx) => {
                const line = event.__line ?? idx;
                return (
                  <tr
                    key={`${line}_${event.event_id}`}
                    onClick={() => onSelectLine(line, event)}
                    style={{
                      cursor: "pointer",
                      background: selectedLine === line ? "#e4ecff" : "transparent",
                    }}
                  >
                    <td style={{ padding: "6px 10px", fontSize: 12 }}>{line}</td>
                    <td style={{ padding: "6px 10px", fontSize: 12 }}>{event.tick_u64}</td>
                    <td style={{ padding: "6px 10px", fontSize: 12 }}>{event.event_type}</td>
                    <td style={{ padding: "6px 10px", fontSize: 12, fontFamily: "monospace" }}>{String(event.artifact_hash).slice(0, 18)}...</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid">
        <JsonBlock title="Node Inspection" value={inspectedArtifact ?? { note: "Select a ledger event" }} canon={!!inspectedArtifact} />
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Bottleneck Radar</h3>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="card" style={{ padding: 10 }}>
              <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>search</div>
              <strong>{axisValue(metrics, "metasearch_cost_ratio_q32")}</strong>
            </div>
            <div className="card" style={{ padding: 10 }}>
              <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>build</div>
              <strong>{axisValue(metrics, "build_link_fraction_q32")}</strong>
            </div>
            <div className="card" style={{ padding: 10 }}>
              <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>hotloop</div>
              <strong>{axisValue(metrics, "hotloop_top_share_q32")}</strong>
            </div>
            <div className="card" style={{ padding: 10 }}>
              <div style={{ color: "var(--ink-muted)", fontSize: 12 }}>science</div>
              <strong>{axisValue(metrics, "science_rmse_q32")}</strong>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
