import fs from "node:fs";
import path from "node:path";
import {
  appendLedgerEvents,
  buildLedgerEventsFromArtifacts,
  writeHashedArtifact,
} from "./artifacts_v18";
import { canonHash } from "../lib/canon_sha256";
import { stateRootForRun } from "./run_scan_v18";

type JsonObj = Record<string, unknown>;

type MockGeneratorOptions = {
  runtimeRootAbs: string;
  seed_u64?: number;
  tick_rate_hz?: number;
  max_ticks?: number;
};

const DEFAULT_SEED = 18_000_001;
const DEFAULT_HZ = 1;
const DEFAULT_MAX_TICKS = 10_000;

const ACTION_CYCLE = ["NOOP", "RUN_CAMPAIGN", "RUN_GOAL_TASK", "NOOP", "RUN_GOAL_TASK"] as const;

class Lcg {
  private state: bigint;

  constructor(seed: number) {
    this.state = BigInt(seed || DEFAULT_SEED) & ((1n << 64n) - 1n);
  }

  nextU64(): bigint {
    // Numerical Recipes LCG variant.
    this.state = (6364136223846793005n * this.state + 1n) & ((1n << 64n) - 1n);
    return this.state;
  }

  nextInt(maxExclusive: number): number {
    if (maxExclusive <= 1) {
      return 0;
    }
    return Number(this.nextU64() % BigInt(maxExclusive));
  }

  nextFloat(): number {
    const v = Number(this.nextU64() >> 11n);
    return v / 9007199254740992;
  }
}

function nowStamp(): string {
  const d = new Date();
  const yy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  const ss = String(d.getUTCSeconds()).padStart(2, "0");
  return `${yy}${mm}${dd}_${hh}${mi}${ss}`;
}

function q32(value: number): { q: number } {
  return { q: Math.max(0, Math.floor(value * 2 ** 32)) };
}

function randHash(rng: Lcg, prefix = "artifact"): string {
  const row = { schema_version: "mock_hash_v1", prefix, a: String(rng.nextU64()), b: String(rng.nextU64()) };
  return canonHash(row);
}

export class MockGeneratorV18 {
  readonly seed_u64: number;
  readonly tick_rate_hz: number;
  readonly max_ticks: number;
  readonly runId: string;
  readonly runAbs: string;
  readonly daemonAbs: string;
  readonly stateRootAbs: string;
  readonly configRootAbs: string;

  private rng: Lcg;
  private tick: number;
  private timer: NodeJS.Timeout | null;
  private prevStateId: string;
  private prevEventId: string | null;
  private activeManifestHash: string;
  private policyHash: string;
  private registryHash: string;
  private objectivesHash: string;
  private budgetsHash: string;
  private allowlistsHash: string;
  private goalQueueHash: string;
  private healthcheckSuiteHash: string;
  private budgetRemaining: {
    cpu_cost_q32: { q: number };
    build_cost_q32: { q: number };
    verifier_cost_q32: { q: number };
    disk_bytes_u64: number;
  };
  private cooldowns: Record<string, { next_tick_allowed_u64: number }>;
  private goals: Record<string, { status: "PENDING" | "DONE"; last_tick_u64: number }>;
  private lastActions: Array<{ tick_u64: number; action_kind: string; summary_code: string }>;

  constructor(opts: MockGeneratorOptions) {
    this.seed_u64 = opts.seed_u64 ?? DEFAULT_SEED;
    this.tick_rate_hz = opts.tick_rate_hz ?? DEFAULT_HZ;
    this.max_ticks = opts.max_ticks ?? DEFAULT_MAX_TICKS;

    this.rng = new Lcg(this.seed_u64);
    this.tick = 0;
    this.timer = null;
    this.prevStateId = "sha256:" + "0".repeat(64);
    this.prevEventId = null;

    this.runId = `omega_mc_mock_${nowStamp()}`;
    this.runAbs = path.join(opts.runtimeRootAbs, "mock_runs", this.runId);
    this.daemonAbs = path.join(this.runAbs, "daemon", "rsi_omega_daemon_v18_0");
    this.stateRootAbs = path.join(this.daemonAbs, "state");
    this.configRootAbs = path.join(this.daemonAbs, "config");

    this.policyHash = "sha256:" + "1".repeat(64);
    this.registryHash = "sha256:" + "2".repeat(64);
    this.objectivesHash = "sha256:" + "3".repeat(64);
    this.budgetsHash = "sha256:" + "4".repeat(64);
    this.allowlistsHash = "sha256:" + "5".repeat(64);
    this.goalQueueHash = "sha256:" + "6".repeat(64);
    this.healthcheckSuiteHash = "sha256:" + "7".repeat(64);
    this.activeManifestHash = "sha256:" + "8".repeat(64);

    this.budgetRemaining = {
      cpu_cost_q32: q32(260_000),
      build_cost_q32: q32(260_000),
      verifier_cost_q32: q32(260_000),
      disk_bytes_u64: 1_073_741_824,
    };

    this.cooldowns = {
      rsi_sas_code_v12_0: { next_tick_allowed_u64: 1 },
      rsi_sas_metasearch_v16_1: { next_tick_allowed_u64: 1 },
      rsi_sas_val_v17_0: { next_tick_allowed_u64: 1 },
    };

    this.goals = {
      goal_code_quality_001: { status: "PENDING", last_tick_u64: 0 },
      goal_metasearch_001: { status: "PENDING", last_tick_u64: 0 },
      goal_val_hotloop_001: { status: "PENDING", last_tick_u64: 0 },
    };

    this.lastActions = [];

    this.initializeRun();
  }

  private initializeRun(): void {
    fs.mkdirSync(this.configRootAbs, { recursive: true });
    fs.mkdirSync(path.join(this.configRootAbs, "goals"), { recursive: true });
    for (const sub of ["state", "observations", "issues", "decisions", "dispatch", "ledger", "snapshot", "subruns"]) {
      fs.mkdirSync(path.join(this.stateRootAbs, sub), { recursive: true });
    }

    const budgets: JsonObj = {
      schema_version: "omega_budgets_v1",
      max_ticks_total: this.max_ticks,
      max_ticks_per_day: 4000,
      max_wallclock_per_tick_s: 120,
      max_cpu_cost_q32_per_day: q32(260_000),
      max_build_cost_q32_per_day: q32(260_000),
      max_verifier_cost_q32_per_day: q32(260_000),
      max_disk_bytes_per_day: 1_073_741_824,
      max_activation_attempts_per_tick: 2,
      max_rollbacks_per_day: 6,
    };

    const registry: JsonObj = {
      schema_version: "omega_capability_registry_v2",
      capabilities: [
        {
          capability_id: "RSI_SAS_VAL",
          campaign_id: "rsi_sas_val_v17_0",
          campaign_pack_rel: "campaigns/rsi_sas_val_v17_0/rsi_sas_val_pack_v17_0.json",
          orchestrator_module: "orchestrator.rsi_sas_val_v17_0",
          verifier_module: "cdel.v17_0.verify_rsi_sas_val_v1",
          promotion_bundle_rel: "daemon/rsi_sas_val_v17_0/state/promotion/*.sas_val_promotion_bundle_v1.json",
          cooldown_ticks_u64: 4,
        },
        {
          capability_id: "RSI_SAS_METASEARCH",
          campaign_id: "rsi_sas_metasearch_v16_1",
          campaign_pack_rel: "campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json",
          orchestrator_module: "orchestrator.rsi_sas_metasearch_v16_1",
          verifier_module: "cdel.v16_1.verify_rsi_sas_metasearch_v1",
          promotion_bundle_rel: "daemon/rsi_sas_metasearch_v16_1/state/promotion/*.sas_metasearch_promotion_bundle_v1.json",
          cooldown_ticks_u64: 4,
        },
      ],
    };

    const policy: JsonObj = {
      schema_version: "omega_policy_ir_v1",
      policy_name: "mock_policy",
      version: "1",
      constraints: {
        max_dispatch_per_tick: 1,
      },
      tie_break_priority: ["GOAL", "ISSUE", "NOOP"],
    };

    const objectives: JsonObj = {
      schema_version: "omega_objectives_v1",
      objectives: [
        { objective_id: "obj_latency", metric_id: "metasearch_cost_ratio_q32", comparator: "LT", threshold_q32: q32(0.5) },
        { objective_id: "obj_hotloop", metric_id: "hotloop_top_share_q32", comparator: "LT", threshold_q32: q32(0.7) },
      ],
    };

    const allowlists: JsonObj = {
      schema_version: "omega_allowlists_v1",
      path_allowlist: ["CDEL-v2/**", "orchestrator/**", "daemon/**", "tools/**", "campaigns/**"],
      path_denylist: ["meta-core/**", "Genesis/**"],
    };

    const goalQueue: JsonObj = {
      schema_version: "omega_goal_queue_v1",
      goals: [
        { goal_id: "goal_code_quality_001", status: "PENDING" },
        { goal_id: "goal_metasearch_001", status: "PENDING" },
        { goal_id: "goal_val_hotloop_001", status: "PENDING" },
      ],
    };

    const healthcheckSuite: JsonObj = {
      schema_version: "healthcheck_suitepack_v1",
      suite_id: "mock_suite",
      checks: [{ id: "smoke", type: "NOOP" }],
    };

    const pack: JsonObj = {
      schema_version: "rsi_omega_daemon_pack_v1",
      omega_policy_ir_rel: "omega_policy_ir_v1.json",
      omega_capability_registry_rel: "omega_capability_registry_v2.json",
      omega_objectives_rel: "omega_objectives_v1.json",
      omega_budgets_rel: "omega_budgets_v1.json",
      omega_allowlists_rel: "omega_allowlists_v1.json",
      healthcheck_suitepack_rel: "healthcheck_suitepack_v1.json",
      baseline_metrics_rel: "baselines/mock_baseline_metrics_v1.json",
      goal_queue_rel: "goals/omega_goal_queue_v1.json",
      allow_unbound_observer_fallback: true,
      seed_u64: this.seed_u64,
    };

    fs.mkdirSync(path.join(this.configRootAbs, "baselines"), { recursive: true });
    fs.writeFileSync(path.join(this.configRootAbs, "baselines", "mock_baseline_metrics_v1.json"), JSON.stringify({ schema_version: "mock_baseline_metrics_v1" }), "utf-8");

    fs.writeFileSync(path.join(this.configRootAbs, "omega_budgets_v1.json"), JSON.stringify(budgets), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "omega_capability_registry_v2.json"), JSON.stringify(registry), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "omega_policy_ir_v1.json"), JSON.stringify(policy), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "omega_objectives_v1.json"), JSON.stringify(objectives), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "omega_allowlists_v1.json"), JSON.stringify(allowlists), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "healthcheck_suitepack_v1.json"), JSON.stringify(healthcheckSuite), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "goals", "omega_goal_queue_v1.json"), JSON.stringify(goalQueue), "utf-8");
    fs.writeFileSync(path.join(this.configRootAbs, "rsi_omega_daemon_pack_v1.json"), JSON.stringify(pack), "utf-8");

    this.policyHash = canonHash(policy);
    this.registryHash = canonHash(registry);
    this.objectivesHash = canonHash(objectives);
    this.budgetsHash = canonHash(budgets);
    this.allowlistsHash = canonHash(allowlists);
    this.goalQueueHash = canonHash(goalQueue);
    this.healthcheckSuiteHash = canonHash(healthcheckSuite);
    this.writeRunArtifacts("NOT_STARTED");
  }

  start(): void {
    if (this.timer) {
      return;
    }
    this.writeTick();
    const interval = Math.max(100, Math.floor(1000 / Math.max(1, this.tick_rate_hz)));
    this.timer = setInterval(() => {
      this.writeTick();
    }, interval);
  }

  stop(): void {
    if (!this.timer) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }

  getRunRootAbs(): string {
    return this.runAbs;
  }

  private writeRunArtifacts(terminationReason: string): void {
    const preflight = {
      schema_version: "OMEGA_PREFLIGHT_REPORT_v1",
      ok_b: true,
      fail_reason: "",
      checks: [{ check_id: "mock_preflight", ok_b: true, detail: "OK" }],
    };
    const diagnostic = {
      schema_version: "OMEGA_DIAGNOSTIC_PACKET_v1",
      created_at_utc: "",
      created_from_tick_u64: this.tick,
      tick_u64: this.tick,
      safe_halt: terminationReason === "SAFE_HALT",
      termination_reason: terminationReason,
      latest_gate_status: { A: "PASS", B: "PASS", C: "PASS", F: "PASS", P: "PASS", Q: "PASS" },
      gate_failures: [],
      verifier_failures: [],
    };
    const gateProof = {
      schema_version: "OMEGA_GATE_PROOF_v1",
      created_at_utc: "",
      created_from_tick_u64: this.tick,
      ticks_completed_u64: this.tick,
      gate_status: { A: "PASS", B: "PASS", C: "PASS", F: "PASS", P: "PASS", Q: "PASS" },
      gate_report_sha256: randHash(this.rng, "mock_gate_report"),
    };
    const replayManifest = {
      schema_version: "OMEGA_REPLAY_MANIFEST_v1",
      run_dir: this.runAbs,
      series_prefix: this.runId,
      profile: "mock",
      meta_core_mode: "mock",
      git: {
        agi_stack_head_sha: "",
        cdel_submodule_sha: "",
      },
      inputs: {
        campaign_pack_path: path.join(this.configRootAbs, "rsi_omega_daemon_pack_v1.json"),
        campaign_pack_sha256: "",
        capability_registry_path: path.join(this.configRootAbs, "omega_capability_registry_v2.json"),
        capability_registry_sha256: "",
        goal_queue_effective_path: path.join(this.configRootAbs, "goals", "omega_goal_queue_v1.json"),
        goal_queue_effective_sha256: "",
      },
      artifacts: [],
      state_roots: [this.stateRootAbs],
    };
    fs.writeFileSync(path.join(this.runAbs, "OMEGA_PREFLIGHT_REPORT_v1.json"), JSON.stringify(preflight), "utf-8");
    fs.writeFileSync(path.join(this.runAbs, "OMEGA_DIAGNOSTIC_PACKET_v1.json"), JSON.stringify(diagnostic), "utf-8");
    fs.writeFileSync(path.join(this.runAbs, "OMEGA_GATE_PROOF_v1.json"), JSON.stringify(gateProof), "utf-8");
    fs.writeFileSync(path.join(this.runAbs, "OMEGA_REPLAY_MANIFEST_v1.json"), JSON.stringify(replayManifest), "utf-8");
  }

  private chooseActionKind(): "NOOP" | "RUN_CAMPAIGN" | "RUN_GOAL_TASK" | "SAFE_HALT" {
    if (this.tick > 0 && this.tick % 37 === 0) {
      return "SAFE_HALT";
    }
    return ACTION_CYCLE[this.tick % ACTION_CYCLE.length];
  }

  private consumeBudget(actionKind: string): void {
    const cpuCost = actionKind === "NOOP" ? 0.1 : actionKind === "SAFE_HALT" ? 0 : 0.5;
    const buildCost = actionKind === "RUN_CAMPAIGN" ? 0.4 : actionKind === "RUN_GOAL_TASK" ? 0.3 : 0.05;
    const verifierCost = actionKind === "RUN_CAMPAIGN" || actionKind === "RUN_GOAL_TASK" ? 0.2 : 0.01;

    this.budgetRemaining.cpu_cost_q32 = q32(Math.max(0, this.budgetRemaining.cpu_cost_q32.q / 2 ** 32 - cpuCost));
    this.budgetRemaining.build_cost_q32 = q32(Math.max(0, this.budgetRemaining.build_cost_q32.q / 2 ** 32 - buildCost));
    this.budgetRemaining.verifier_cost_q32 = q32(Math.max(0, this.budgetRemaining.verifier_cost_q32.q / 2 ** 32 - verifierCost));
    this.budgetRemaining.disk_bytes_u64 = Math.max(32_000_000, this.budgetRemaining.disk_bytes_u64 - this.rng.nextInt(30000));
  }

  private markGoalDone(goalId: string | null): void {
    if (!goalId || !this.goals[goalId]) {
      return;
    }
    this.goals[goalId] = { status: "DONE", last_tick_u64: this.tick };
  }

  private writeTick(): void {
    if (this.tick >= this.max_ticks) {
      this.stop();
      return;
    }
    this.tick += 1;

    for (const sub of ["state", "observations", "issues", "decisions", "dispatch", "ledger", "snapshot", "subruns"]) {
      fs.mkdirSync(path.join(this.stateRootAbs, sub), { recursive: true });
    }

    const actionKind = this.chooseActionKind();

    const pendingGoals = Object.entries(this.goals)
      .filter(([, row]) => row.status === "PENDING")
      .map(([id]) => id);
    const chosenGoal = pendingGoals.length > 0 ? pendingGoals[this.rng.nextInt(pendingGoals.length)] : null;

    const campaignId = actionKind === "RUN_CAMPAIGN" ? "rsi_sas_metasearch_v16_1" : actionKind === "RUN_GOAL_TASK" ? "rsi_sas_val_v17_0" : null;
    const capabilityId = actionKind === "RUN_CAMPAIGN" ? "RSI_SAS_METASEARCH" : actionKind === "RUN_GOAL_TASK" ? "RSI_SAS_VAL" : null;

    this.consumeBudget(actionKind);

    const statePayload: JsonObj = {
      schema_version: "omega_state_v1",
      state_id: "sha256:" + "0".repeat(64),
      tick_u64: this.tick,
      prev_state_id: this.prevStateId,
      active_manifest_hash: this.activeManifestHash,
      policy_hash: this.policyHash,
      registry_hash: this.registryHash,
      objectives_hash: this.objectivesHash,
      budgets_hash: this.budgetsHash,
      allowlists_hash: this.allowlistsHash,
      cooldowns: this.cooldowns,
      budget_remaining: this.budgetRemaining,
      last_actions: this.lastActions,
      goal_queue_hash: this.goalQueueHash,
      goals: this.goals,
    };

    const stateRow = writeHashedArtifact(path.join(this.stateRootAbs, "state"), "omega_state_v1", statePayload, "state_id");
    const stateObj = stateRow.payload;
    this.prevStateId = String(stateObj.state_id);

    const observationPayload: JsonObj = {
      schema_version: "omega_observation_report_v1",
      report_id: "sha256:" + "0".repeat(64),
      tick_u64: this.tick,
      active_manifest_hash: this.activeManifestHash,
      metrics: {
        metasearch_cost_ratio_q32: q32(0.1 + this.rng.nextFloat() * 0.9),
        hotloop_top_share_q32: q32(0.2 + this.rng.nextFloat() * 0.7),
        build_link_fraction_q32: q32(this.rng.nextFloat()),
        verifier_overhead_q32: q32(this.rng.nextFloat() * 0.2),
        science_rmse_q32: q32(this.rng.nextFloat() * 0.2),
        promotion_reject_rate_rat: { num_u64: this.rng.nextInt(2), den_u64: 1 },
      },
      metric_series: {
        metasearch_cost_ratio_q32: [q32(0.2 + this.rng.nextFloat() * 0.6)],
        hotloop_top_share_q32: [q32(0.3 + this.rng.nextFloat() * 0.5)],
        build_link_fraction_q32: [q32(this.rng.nextFloat())],
        science_rmse_q32: [q32(this.rng.nextFloat() * 0.1)],
      },
      sources: [
        {
          producer_campaign_id: campaignId ?? "rsi_sas_system_v14_0",
          producer_run_id: `${campaignId ?? "rsi_sas_system_v14_0"}_tick_${String(this.tick).padStart(4, "0")}`,
          schema_id: "mock_metric_source_v1",
          artifact_hash: randHash(this.rng, "metric_source"),
        },
      ],
      inputs_hashes: {
        policy_hash: this.policyHash,
        registry_hash: this.registryHash,
        objectives_hash: this.objectivesHash,
      },
    };
    const observationRow = writeHashedArtifact(path.join(this.stateRootAbs, "observations"), "omega_observation_report_v1", observationPayload, "report_id");

    const issues: JsonObj[] = [];
    const metricValue = (observationPayload.metrics as JsonObj).metasearch_cost_ratio_q32 as { q: number };
    if ((metricValue?.q ?? 0) > q32(0.7).q) {
      issues.push({
        issue_id: randHash(this.rng, "issue"),
        issue_type: "SEARCH_SLOW",
        metric_id: "metasearch_cost_ratio_q32",
        severity_q32: metricValue,
        persistence_ticks_u64: 1,
        evidence: [String(observationRow.payload.report_id)],
      });
    }

    const issuePayload: JsonObj = {
      schema_version: "omega_issue_bundle_v1",
      bundle_id: "sha256:" + "0".repeat(64),
      tick_u64: this.tick,
      issues,
    };
    const issueRow = writeHashedArtifact(path.join(this.stateRootAbs, "issues"), "omega_issue_bundle_v1", issuePayload, "bundle_id");

    const planNoId: JsonObj = {
      tick_u64: this.tick,
      observation_report_hash: observationRow.hash,
      issue_bundle_hash: issueRow.hash,
      policy_hash: this.policyHash,
      registry_hash: this.registryHash,
      budgets_hash: this.budgetsHash,
      action_kind: actionKind,
      campaign_id: campaignId,
      capability_id: capabilityId,
      goal_id: chosenGoal,
      assigned_capability_id: capabilityId,
    };

    const planHash = canonHash(planNoId);
    const decisionPayload: JsonObj = {
      schema_version: "omega_decision_plan_v1",
      plan_id: planHash,
      tick_u64: this.tick,
      observation_report_hash: observationRow.hash,
      issue_bundle_hash: issueRow.hash,
      policy_hash: this.policyHash,
      registry_hash: this.registryHash,
      budgets_hash: this.budgetsHash,
      action_kind: actionKind,
      campaign_id: campaignId,
      capability_id: capabilityId,
      assigned_capability_id: capabilityId,
      goal_id: chosenGoal,
      tie_break_path: [
        chosenGoal ? `GOAL:${chosenGoal}` : "NO_GOAL",
        issues.length > 0 ? "ISSUES_PRESENT" : "NO_ISSUES",
      ],
      recompute_proof: {
        inputs_hash: canonHash(planNoId),
        plan_hash: planHash,
      },
      priority_q32: q32(0.5 + this.rng.nextFloat() * 0.5),
    };
    const decisionRow = writeHashedArtifact(path.join(this.stateRootAbs, "decisions"), "omega_decision_plan_v1", decisionPayload);

    let dispatchHash: string | null = null;
    let subverifierHash: string | null = null;
    let promotionHash: string | null = null;
    let activationHash: string | null = null;
    let rollbackHash: string | null = null;

    if (actionKind === "RUN_CAMPAIGN" || actionKind === "RUN_GOAL_TASK") {
      const actionId = decisionRow.hash.split(":", 2)[1].slice(0, 16);
      const dispatchDir = path.join(this.stateRootAbs, "dispatch", actionId);
      fs.mkdirSync(dispatchDir, { recursive: true });
      fs.mkdirSync(path.join(dispatchDir, "verifier"), { recursive: true });
      fs.mkdirSync(path.join(dispatchDir, "promotion"), { recursive: true });
      fs.mkdirSync(path.join(dispatchDir, "activation"), { recursive: true });

      const subrunRootRel = `subruns/${actionId}_${campaignId}`;
      const subrunStateRel = `daemon/${campaignId}/state`;
      const subrunRootAbs = path.join(this.stateRootAbs, subrunRootRel);
      fs.mkdirSync(path.join(subrunRootAbs, subrunStateRel, "promotion"), { recursive: true });
      fs.mkdirSync(path.join(subrunRootAbs, subrunStateRel, "proofs"), { recursive: true });

      const touchedPath = "orchestrator/mock_candidate.py";
      fs.mkdirSync(path.join(subrunRootAbs, path.dirname(touchedPath)), { recursive: true });
      fs.writeFileSync(path.join(subrunRootAbs, touchedPath), `# tick ${this.tick}\nprint('mock candidate')\n`, "utf-8");
      fs.writeFileSync(
        path.join(subrunRootAbs, subrunStateRel, "proofs", `tick_${String(this.tick).padStart(4, "0")}.lean`),
        `theorem tick_${this.tick} : True := by trivial\n`,
        "utf-8",
      );

      const promotionBundle = {
        schema_version: "sas_val_promotion_bundle_v1",
        campaign_id: campaignId,
        tick_u64: this.tick,
        touched_paths: [touchedPath, "CDEL-v2/cdel/v18_0/mock_receipt.json"],
        patch_paths: ["daemon/mock.patch"],
        files: [touchedPath],
      };
      const promotionBundleRow = writeHashedArtifact(
        path.join(subrunRootAbs, subrunStateRel, "promotion"),
        "sas_val_promotion_bundle_v1",
        promotionBundle,
      );

      const dispatchStdout = [
        "OK",
        `state_dir: ${path.join(subrunRootAbs, subrunStateRel)}`,
        `promotion_bundle: ${promotionBundleRow.pathAbs}`,
        `promotion_bundle_hash: ${promotionBundleRow.hash}`,
      ].join("\n");
      fs.writeFileSync(path.join(dispatchDir, "stdout.log"), dispatchStdout + "\n", "utf-8");
      fs.writeFileSync(path.join(dispatchDir, "stderr.log"), "", "utf-8");

      const dispatchReceipt = {
        schema_version: "omega_dispatch_receipt_v1",
        receipt_id: "sha256:" + "0".repeat(64),
        tick_u64: this.tick,
        campaign_id: campaignId,
        capability_id: capabilityId,
        invocation: {
          py_module: `orchestrator.${campaignId}`,
          argv: ["--campaign_pack", `../../../../../campaigns/${campaignId}/pack.json`, "--out_dir", `../../../../../.omega_v18_exec_workspace/${actionId}`],
          env_fingerprint_hash: randHash(this.rng, "env"),
        },
        subrun: {
          subrun_root_rel: subrunRootRel,
          state_dir_rel: subrunStateRel,
          subrun_tree_hash: randHash(this.rng, "tree"),
        },
        stdout_hash: canonHash(dispatchStdout),
        stderr_hash: canonHash(""),
        return_code: 0,
      };
      const dispatchRow = writeHashedArtifact(dispatchDir, "omega_dispatch_receipt_v1", dispatchReceipt, "receipt_id");
      dispatchHash = dispatchRow.hash;

      const subverifierStatus = this.rng.nextFloat() < 0.92 ? "VALID" : "INVALID";
      const verifierStdout = `${subverifierStatus}\n`;
      fs.writeFileSync(path.join(dispatchDir, "verifier", "stdout.log"), verifierStdout, "utf-8");
      fs.writeFileSync(path.join(dispatchDir, "verifier", "stderr.log"), "", "utf-8");

      const subverifierReceipt = {
        schema_version: "omega_subverifier_receipt_v1",
        receipt_id: "sha256:" + "0".repeat(64),
        tick_u64: this.tick,
        campaign_id: campaignId,
        verifier_module: `cdel.v17_0.verify_${campaignId}_v1`,
        verifier_mode: "full",
        state_dir_hash: randHash(this.rng, "state_dir"),
        result: {
          status: subverifierStatus,
          reason_code: subverifierStatus === "VALID" ? null : "MOCK_FAIL",
        },
        stdout_hash: canonHash(verifierStdout),
        stderr_hash: canonHash(""),
      };
      const subverifierRow = writeHashedArtifact(path.join(dispatchDir, "verifier"), "omega_subverifier_receipt_v1", subverifierReceipt, "receipt_id");
      subverifierHash = subverifierRow.hash;

      const promoted = subverifierStatus === "VALID" && this.rng.nextFloat() < 0.6;
      const promotionStatus = promoted ? "PROMOTED" : this.rng.nextFloat() < 0.5 ? "REJECTED" : "SKIPPED";

      const promotionStdout = `${promotionStatus}\n`;
      fs.writeFileSync(path.join(dispatchDir, "promotion", "stdout.log"), promotionStdout, "utf-8");
      fs.writeFileSync(path.join(dispatchDir, "promotion", "stderr.log"), "", "utf-8");

      if (promotionStatus === "PROMOTED") {
        this.activeManifestHash = randHash(this.rng, "manifest");
      }

      const promotionReceipt = {
        schema_version: "omega_promotion_receipt_v1",
        receipt_id: "sha256:" + "0".repeat(64),
        tick_u64: this.tick,
        promotion_bundle_hash: promotionBundleRow.hash,
        meta_core_verifier_fingerprint: {
          constitution_meta_hash: randHash(this.rng, "constitution"),
          binary_hash_or_build_id: randHash(this.rng, "binary"),
        },
        result: {
          status: promotionStatus,
          reason_code: promotionStatus === "PROMOTED" ? null : "MOCK_CONDITION",
        },
        active_manifest_hash_after: this.activeManifestHash,
      };
      const promotionRow = writeHashedArtifact(path.join(dispatchDir, "promotion"), "omega_promotion_receipt_v1", promotionReceipt, "receipt_id");
      promotionHash = promotionRow.hash;

      if (promotionStatus === "PROMOTED") {
        const activationPass = this.rng.nextFloat() < 0.93;
        const activationReceipt = {
          schema_version: "omega_activation_receipt_v1",
          receipt_id: "sha256:" + "0".repeat(64),
          tick_u64: this.tick,
          before_active_manifest_hash: statePayload.active_manifest_hash,
          after_active_manifest_hash: this.activeManifestHash,
          healthcheck_suite_hash: this.healthcheckSuiteHash,
          healthcheck_result: activationPass ? "PASS" : "FAIL",
          activation_method: "ATOMIC_POINTER_SWAP",
          activation_success: activationPass,
          pass: activationPass,
          reasons: [activationPass ? "HEALTHCHECK_PASS" : "HEALTHCHECK_FAIL"],
        };
        const activationRow = writeHashedArtifact(path.join(dispatchDir, "activation"), "omega_activation_receipt_v1", activationReceipt, "receipt_id");
        activationHash = activationRow.hash;

        if (!activationPass) {
          const rollbackReceipt = {
            schema_version: "omega_rollback_receipt_v1",
            receipt_id: "sha256:" + "0".repeat(64),
            tick_u64: this.tick,
            rollback_from_manifest_hash: this.activeManifestHash,
            rollback_to_manifest_hash: String(statePayload.active_manifest_hash),
            cause: "HEALTHCHECK_FAIL",
            meta_core_verdict_hash: randHash(this.rng, "verdict"),
          };
          const rollbackRow = writeHashedArtifact(path.join(dispatchDir, "activation"), "omega_rollback_receipt_v1", rollbackReceipt, "receipt_id");
          rollbackHash = rollbackRow.hash;
          this.activeManifestHash = String(statePayload.active_manifest_hash);
        }
      }

      if (chosenGoal && (actionKind === "RUN_GOAL_TASK" || actionKind === "RUN_CAMPAIGN")) {
        this.markGoalDone(chosenGoal);
      }
      this.cooldowns[campaignId as string] = { next_tick_allowed_u64: this.tick + 3 };
    }

    this.lastActions.push({ tick_u64: this.tick, action_kind: actionKind, summary_code: "OK" });
    this.lastActions = this.lastActions.slice(-12);

    const traceArtifactHashes = [stateRow.hash, observationRow.hash, issueRow.hash, decisionRow.hash]
      .concat(dispatchHash ? [dispatchHash] : [])
      .concat(subverifierHash ? [subverifierHash] : [])
      .concat(promotionHash ? [promotionHash] : [])
      .concat(activationHash ? [activationHash] : [])
      .concat(rollbackHash ? [rollbackHash] : []);

    const traceH0 = canonHash({
      schema_version: "omega_trace_seed_v1",
      run_seed_u64: this.seed_u64,
      pack_hash: canonHash(JSON.parse(fs.readFileSync(path.join(this.configRootAbs, "rsi_omega_daemon_pack_v1.json"), "utf-8"))),
      policy_hash: this.policyHash,
      registry_hash: this.registryHash,
      objectives_hash: this.objectivesHash,
      tick_u64: this.tick,
      prev_state_hash: stateRow.hash,
    });

    let head = traceH0;
    for (const h of traceArtifactHashes) {
      head = canonHash({ schema_version: "omega_trace_step_v1", prev: head, artifact_hash: h });
    }

    const tracePayload = {
      schema_version: "omega_trace_hash_chain_v1",
      H0: traceH0,
      artifact_hashes: traceArtifactHashes,
      H_final: head,
    };
    const traceRow = writeHashedArtifact(path.join(this.stateRootAbs, "ledger"), "omega_trace_hash_chain_v1", tracePayload);

    const snapshotPayload = {
      schema_version: "omega_tick_snapshot_v1",
      snapshot_id: "sha256:" + "0".repeat(64),
      tick_u64: this.tick,
      state_hash: stateRow.hash,
      observation_report_hash: observationRow.hash,
      issue_bundle_hash: issueRow.hash,
      decision_plan_hash: decisionRow.hash,
      dispatch_receipt_hash: dispatchHash,
      subverifier_receipt_hash: subverifierHash,
      promotion_receipt_hash: promotionHash,
      activation_receipt_hash: activationHash,
      rollback_receipt_hash: rollbackHash,
      trace_hash_chain_hash: traceRow.hash,
      budget_remaining: this.budgetRemaining,
      cooldowns: this.cooldowns,
      goal_queue_hash: this.goalQueueHash,
    };
    const snapshotRow = writeHashedArtifact(path.join(this.stateRootAbs, "snapshot"), "omega_tick_snapshot_v1", snapshotPayload, "snapshot_id");

    const safeHaltHash = actionKind === "SAFE_HALT" ? decisionRow.hash : null;
    const rows = buildLedgerEventsFromArtifacts(
      this.tick,
      {
        state: stateRow.hash,
        observation: observationRow.hash,
        issue: issueRow.hash,
        decision: decisionRow.hash,
        dispatch: dispatchHash,
        subverifier: subverifierHash,
        promotion: promotionHash,
        activation: activationHash,
        rollback: rollbackHash,
        snapshot: snapshotRow.hash,
        safe_halt: safeHaltHash,
      },
      this.prevEventId,
    );

    appendLedgerEvents(path.join(stateRootForRun(this.runAbs), "ledger", "omega_ledger_v1.jsonl"), rows.events);
    this.prevEventId = rows.prevEventId || this.prevEventId;
    this.writeRunArtifacts(actionKind === "SAFE_HALT" ? "SAFE_HALT" : "IN_PROGRESS");

    if (actionKind === "SAFE_HALT") {
      this.stop();
    }
  }
}
