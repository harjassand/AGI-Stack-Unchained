import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { buildSnapshotPayload, discoverRunArtifactsForMembers } from "../../server/artifacts_v18";
import { MockGeneratorV18 } from "../../server/mock_generator_v18";

const temps: string[] = [];

afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe("artifacts snapshot resolver", () => {
  it("loads latest snapshot plus resolved artifacts", async () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "omega-mc-artifacts-"));
    temps.push(tmp);

    const gen = new MockGeneratorV18({ runtimeRootAbs: tmp, tick_rate_hz: 10, max_ticks: 2 });
    gen.start();
    await new Promise((resolve) => setTimeout(resolve, 220));
    gen.stop();

    const payload = buildSnapshotPayload(gen.getRunRootAbs());

    expect(payload.latest_snapshot).not.toBeNull();
    expect(payload.artifacts.omega_state_v1).not.toBeNull();
    expect(payload.artifacts.omega_decision_plan_v1).not.toBeNull();
    expect(payload.artifacts.omega_trace_hash_chain_v1).not.toBeNull();
    expect(payload.run_artifacts?.omega_preflight_report_v1).not.toBeNull();
    expect(payload.run_artifacts?.omega_gate_proof_v1).not.toBeNull();
    expect(payload.run_artifacts?.omega_diagnostic_packet_v1).not.toBeNull();
    expect(payload.run_artifacts?.omega_replay_manifest_v1).not.toBeNull();
    const filenames = (payload.run_artifacts?.artifact_index ?? []).map((row) => row.filename);
    expect(filenames).toEqual([
      "OMEGA_DIAGNOSTIC_PACKET_v1.json",
      "OMEGA_GATE_PROOF_v1.json",
      "OMEGA_PREFLIGHT_REPORT_v1.json",
      "OMEGA_REPLAY_MANIFEST_v1.json",
    ]);
  });

  it("orders run artifact discovery by newest run then filename", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "omega-mc-artifacts-order-"));
    temps.push(tmp);
    const runA = path.join(tmp, "series_tick_0001");
    const runB = path.join(tmp, "series_tick_0002");
    fs.mkdirSync(runA, { recursive: true });
    fs.mkdirSync(runB, { recursive: true });
    fs.writeFileSync(path.join(runA, "OMEGA_PREFLIGHT_REPORT_v1.json"), JSON.stringify({ schema_version: "OMEGA_PREFLIGHT_REPORT_v1" }), "utf-8");
    fs.writeFileSync(path.join(runB, "OMEGA_PREFLIGHT_REPORT_v1.json"), JSON.stringify({ schema_version: "OMEGA_PREFLIGHT_REPORT_v1" }), "utf-8");
    fs.writeFileSync(path.join(runB, "OMEGA_DIAGNOSTIC_PACKET_v1.json"), JSON.stringify({ schema_version: "OMEGA_DIAGNOSTIC_PACKET_v1" }), "utf-8");

    const rows = discoverRunArtifactsForMembers([
      { run_id: "series_tick_0001", run_abs: runA, order_u64: 1 },
      { run_id: "series_tick_0002", run_abs: runB, order_u64: 2 },
    ]);
    expect(rows.map((row) => `${row.run_id}:${row.filename}`)).toEqual([
      "series_tick_0002:OMEGA_DIAGNOSTIC_PACKET_v1.json",
      "series_tick_0002:OMEGA_PREFLIGHT_REPORT_v1.json",
      "series_tick_0001:OMEGA_PREFLIGHT_REPORT_v1.json",
    ]);
  });

  it("loads GE audit report when present at run root", async () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "omega-mc-ge-audit-"));
    temps.push(tmp);

    const gen = new MockGeneratorV18({ runtimeRootAbs: tmp, tick_rate_hz: 10, max_ticks: 2 });
    gen.start();
    await new Promise((resolve) => setTimeout(resolve, 220));
    gen.stop();

    const geAuditPath = path.join(gen.getRunRootAbs(), "GE_AUDIT_REPORT_v1.json");
    fs.writeFileSync(
      geAuditPath,
      JSON.stringify(
        {
          schema_version: "ge_audit_report_v1",
          kpi: {
            promote_u64: 2,
            total_wall_ms_u64: 1000,
            yield_promotions_per_wall_ms_q32: 8589934,
          },
          novelty: {
            novelty_coverage_q32: 2147483648,
          },
          falsification_flags: [],
        },
        null,
        2,
      ),
      "utf-8",
    );

    const payload = buildSnapshotPayload(gen.getRunRootAbs());
    expect(payload.ge_audit_report_v1).not.toBeNull();
    expect((payload.ge_audit_report_v1 as Record<string, unknown>).schema_version).toBe("ge_audit_report_v1");
  });
});
