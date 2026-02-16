import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type CreateRunOpts = {
  tick_u64: number;
  dispatch_dir?: string;
  campaign_id?: string;
  capability_id?: string;
};

function shaHex(input: string): string {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function writeJson(pathAbs: string, payload: Record<string, unknown>): void {
  fs.mkdirSync(path.dirname(pathAbs), { recursive: true });
  fs.writeFileSync(pathAbs, JSON.stringify(payload), "utf-8");
}

export function mkTempRunsRoot(prefix = "omega-mc-series-"): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

export function rmTree(pathAbs: string): void {
  fs.rmSync(pathAbs, { recursive: true, force: true });
}

export function createOmegaRun(runsRootAbs: string, runId: string, opts: CreateRunOpts): string {
  const tick = Math.floor(opts.tick_u64);
  const campaignId = opts.campaign_id ?? "camp_alpha";
  const capabilityId = opts.capability_id ?? "CAP_ALPHA";
  const dispatchDir = opts.dispatch_dir ?? "dispatch_001";

  const runAbs = path.join(runsRootAbs, runId);
  const daemonRoot = path.join(runAbs, "daemon", "rsi_omega_daemon_v18_0");
  const configRoot = path.join(daemonRoot, "config");
  const stateRoot = path.join(daemonRoot, "state");
  const dispatchRoot = path.join(stateRoot, "dispatch", dispatchDir);

  fs.mkdirSync(configRoot, { recursive: true });
  fs.mkdirSync(path.join(stateRoot, "ledger"), { recursive: true });
  fs.mkdirSync(path.join(stateRoot, "snapshot"), { recursive: true });
  fs.mkdirSync(path.join(stateRoot, "decisions"), { recursive: true });
  fs.mkdirSync(dispatchRoot, { recursive: true });

  writeJson(path.join(configRoot, "rsi_omega_daemon_pack_v1.json"), {
    schema_version: "rsi_omega_daemon_pack_v1",
  });

  fs.writeFileSync(path.join(stateRoot, "ledger", "omega_ledger_v1.jsonl"), "", "utf-8");

  const decisionHex = shaHex(`${runId}:decision`);
  const dispatchHex = shaHex(`${runId}:dispatch`);
  const promotionHex = shaHex(`${runId}:promotion`);
  const bundleHex = shaHex(`${runId}:bundle`);
  const snapshotHex = shaHex(`${runId}:snapshot`);

  writeJson(path.join(stateRoot, "decisions", `sha256_${decisionHex}.omega_decision_plan_v1.json`), {
    schema_version: "omega_decision_plan_v1",
    tick_u64: tick,
    action_kind: "RUN_CAMPAIGN",
    campaign_id: campaignId,
    capability_id: capabilityId,
    runaway_selected_metric_id: "metric_alpha_q32",
    runaway_escalation_level_u64: 2,
  });

  writeJson(path.join(dispatchRoot, `sha256_${dispatchHex}.omega_dispatch_receipt_v1.json`), {
    schema_version: "omega_dispatch_receipt_v1",
    tick_u64: tick,
    campaign_id: campaignId,
    capability_id: capabilityId,
    return_code: 0,
    invocation: { env_overrides: { TEST_FLAG: "1" } },
    subrun: {
      subrun_root_rel: `subruns/${dispatchDir}_subrun`,
      state_dir_rel: "state",
    },
  });
  fs.writeFileSync(path.join(dispatchRoot, "stdout.log"), "dispatch stdout", "utf-8");
  fs.writeFileSync(path.join(dispatchRoot, "stderr.log"), "dispatch stderr", "utf-8");
  fs.mkdirSync(path.join(dispatchRoot, "verifier"), { recursive: true });
  fs.writeFileSync(path.join(dispatchRoot, "verifier", "stdout.log"), "verifier stdout", "utf-8");
  fs.writeFileSync(path.join(dispatchRoot, "verifier", "stderr.log"), "verifier stderr", "utf-8");

  writeJson(path.join(dispatchRoot, "verifier", `sha256_${shaHex(`${runId}:sub`) }.omega_subverifier_receipt_v1.json`), {
    schema_version: "omega_subverifier_receipt_v1",
    tick_u64: tick,
    result: {
      status: "VALID",
      reason_code: null,
    },
  });

  writeJson(path.join(dispatchRoot, "promotion", `sha256_${promotionHex}.omega_promotion_receipt_v1.json`), {
    schema_version: "omega_promotion_receipt_v1",
    tick_u64: tick,
    promotion_bundle_hash: `sha256:${bundleHex}`,
    result: {
      status: "PROMOTED",
      reason_code: null,
    },
  });

  writeJson(path.join(dispatchRoot, "activation", `sha256_${shaHex(`${runId}:activation`)}.omega_activation_receipt_v1.json`), {
    schema_version: "omega_activation_receipt_v1",
    tick_u64: tick,
    pass: true,
  });

  writeJson(path.join(stateRoot, "subruns", `${dispatchDir}_bundle`, `sha256_${bundleHex}.bundle_payload.json`), {
    touched_paths: ["README.md"],
  });

  writeJson(path.join(stateRoot, "snapshot", `sha256_${snapshotHex}.omega_tick_snapshot_v1.json`), {
    schema_version: "omega_tick_snapshot_v1",
    tick_u64: tick,
    snapshot_id: `sha256:${snapshotHex}`,
    state_hash: null,
    observation_report_hash: null,
    issue_bundle_hash: null,
    decision_plan_hash: `sha256:${decisionHex}`,
    dispatch_receipt_hash: `sha256:${dispatchHex}`,
    subverifier_receipt_hash: `sha256:${shaHex(`${runId}:sub`)}`,
    promotion_receipt_hash: `sha256:${promotionHex}`,
    activation_receipt_hash: `sha256:${shaHex(`${runId}:activation`)}`,
    rollback_receipt_hash: null,
    trace_hash_chain_hash: null,
    budget_remaining: {},
    goal_queue_hash: null,
    cooldowns: {},
  });

  writeJson(path.join(stateRoot, "runaway", `sha256_${shaHex(`${runId}:runaway`)}.omega_runaway_state_v1.json`), {
    schema_version: "omega_runaway_state_v1",
    tick_u64: tick,
    version_minor_u64: 1,
    metric_states: {
      metric_alpha_q32: {
        current_target_q32: { q: 1000 },
        best_value_q32: { q: 900 },
        last_value_q32: { q: 950 },
        stall_ticks_u64: 2,
        escalation_level_u64: 2,
      },
    },
    campaign_intensity_levels: { [campaignId]: 2 },
  });

  return runAbs;
}
