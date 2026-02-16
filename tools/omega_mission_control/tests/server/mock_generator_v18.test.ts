import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { MockGeneratorV18 } from "../../server/mock_generator_v18";

const temps: string[] = [];

afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe("mock generator v18", () => {
  it("creates daemon-shaped artifacts and ledger stream", async () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "omega-mc-"));
    temps.push(tmp);

    const gen = new MockGeneratorV18({
      runtimeRootAbs: tmp,
      seed_u64: 18000001,
      tick_rate_hz: 20,
      max_ticks: 3,
    });

    gen.start();
    await new Promise((resolve) => setTimeout(resolve, 250));
    gen.stop();

    const runAbs = gen.getRunRootAbs();
    const ledgerPath = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "state", "ledger", "omega_ledger_v1.jsonl");
    const configPath = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "config", "rsi_omega_daemon_pack_v1.json");
    const snapshotDir = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0", "state", "snapshot");
    const preflightPath = path.join(runAbs, "OMEGA_PREFLIGHT_REPORT_v1.json");
    const diagnosticPath = path.join(runAbs, "OMEGA_DIAGNOSTIC_PACKET_v1.json");
    const gateProofPath = path.join(runAbs, "OMEGA_GATE_PROOF_v1.json");
    const replayManifestPath = path.join(runAbs, "OMEGA_REPLAY_MANIFEST_v1.json");

    expect(fs.existsSync(configPath)).toBe(true);
    expect(fs.existsSync(ledgerPath)).toBe(true);
    expect(fs.readdirSync(snapshotDir).some((name) => name.endsWith(".omega_tick_snapshot_v1.json"))).toBe(true);
    expect(fs.existsSync(preflightPath)).toBe(true);
    expect(fs.existsSync(diagnosticPath)).toBe(true);
    expect(fs.existsSync(gateProofPath)).toBe(true);
    expect(fs.existsSync(replayManifestPath)).toBe(true);

    const ledgerLines = fs.readFileSync(ledgerPath, "utf-8").split(/\r?\n/).filter(Boolean);
    expect(ledgerLines.length).toBeGreaterThan(0);
  });
});
