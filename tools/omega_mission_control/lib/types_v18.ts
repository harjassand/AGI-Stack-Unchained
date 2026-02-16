export const WS_VERSION = "omega_mc_ws_v1" as const;

export type WsVersion = typeof WS_VERSION;

export type OmegaMode = "mock" | "fs";

export type LedgerEventType =
  | "STATE"
  | "OBSERVATION"
  | "ISSUE"
  | "DECISION"
  | "DISPATCH"
  | "SUBVERIFIER"
  | "PROMOTION"
  | "ACTIVATION"
  | "ROLLBACK"
  | "SNAPSHOT"
  | "SAFE_HALT";

export type OmegaLedgerEventV1 = {
  schema_version: "omega_ledger_event_v1";
  event_id: string;
  tick_u64: number;
  event_type: LedgerEventType;
  artifact_hash: string;
  prev_event_id: string | null;
};

export type OmegaDiagnosticPacketV1 = {
  schema_version: "OMEGA_DIAGNOSTIC_PACKET_v1";
  tick_u64: number;
  termination_reason: string;
  safe_halt: boolean;
  latest_gate_status: Record<string, string>;
  gate_failures: Array<Record<string, unknown>>;
  verifier_failures: Array<Record<string, unknown>>;
};

export type OmegaGateProofV1 = {
  schema_version: "OMEGA_GATE_PROOF_v1";
  created_from_tick_u64: number;
  ticks_completed_u64: number;
  gate_status: Record<string, string>;
  gate_report_sha256: string;
};

export type OmegaPreflightReportV1 = {
  schema_version: "OMEGA_PREFLIGHT_REPORT_v1";
  ok_b: boolean;
  fail_reason: string;
  checks: Array<{ check_id: string; ok_b: boolean; detail: string }>;
};

export type OmegaReplayManifestV1 = {
  schema_version: "OMEGA_REPLAY_MANIFEST_v1";
  run_dir: string;
  series_prefix: string;
  profile: string;
  meta_core_mode: string;
  git: {
    agi_stack_head_sha: string;
    cdel_submodule_sha: string;
  };
  inputs: {
    campaign_pack_path: string;
    campaign_pack_sha256: string;
    capability_registry_path: string;
    capability_registry_sha256: string;
    goal_queue_effective_path: string;
    goal_queue_effective_sha256: string;
  };
  artifacts: Array<{ path: string; sha256: string }>;
  state_roots: string[];
};

export type RunArtifactIndexEntryV18 = {
  run_id: string;
  filename: string;
  path_rel: string;
};

export type SnapshotPayload = {
  latest_snapshot: Record<string, unknown> | null;
  snapshot_hash: string | null;
  artifacts: {
    omega_state_v1: Record<string, unknown> | null;
    omega_observation_report_v1: Record<string, unknown> | null;
    omega_issue_bundle_v1: Record<string, unknown> | null;
    omega_decision_plan_v1: Record<string, unknown> | null;
    omega_dispatch_receipt_v1: Record<string, unknown> | null;
    omega_subverifier_receipt_v1: Record<string, unknown> | null;
    omega_promotion_receipt_v1: Record<string, unknown> | null;
    omega_activation_receipt_v1: Record<string, unknown> | null;
    omega_rollback_receipt_v1: Record<string, unknown> | null;
    omega_trace_hash_chain_v1: Record<string, unknown> | null;
    omega_runaway_state_v1: Record<string, unknown> | null;
  };
  config: {
    omega_budgets_v1: Record<string, unknown> | null;
    omega_capability_registry_v2: Record<string, unknown> | null;
    omega_goal_queue_v1: Record<string, unknown> | null;
    omega_objectives_v1: Record<string, unknown> | null;
    omega_runaway_config_v1: Record<string, unknown> | null;
  };
  run_artifacts?: {
    omega_diagnostic_packet_v1: OmegaDiagnosticPacketV1 | null;
    omega_gate_proof_v1: OmegaGateProofV1 | null;
    omega_preflight_report_v1: OmegaPreflightReportV1 | null;
    omega_replay_manifest_v1: OmegaReplayManifestV1 | null;
    artifact_index: RunArtifactIndexEntryV18[];
  };
  ticks: number[];
  by_tick: Array<{
    tick_u64: number;
    snapshot_hash: string;
    snapshot: Record<string, unknown>;
    member_run_id?: string;
  }>;
  series?: {
    series_id: string;
    tick_count: number;
    tick_min: number;
    tick_max: number;
  };
  runaway_state_history?: Array<Record<string, unknown>>;
  dispatch_timeline?: Array<Record<string, unknown>>;
  ledger_tail?: Array<Record<string, unknown>>;
  ge_audit_report_v1?: Record<string, unknown> | null;
  llm_router_plan_v1?: Record<string, unknown> | null;
  llm_tool_trace_v1?: Array<Record<string, unknown>>;
};

export type WsClientHello = {
  v: WsVersion;
  type: "HELLO";
  run_id: string;
  from_line: number;
  send_full_snapshot: boolean;
};

export type WsClientPause = {
  v: WsVersion;
  type: "SET_PAUSE";
  paused: boolean;
};

export type WsClientRequestArtifact = {
  v: WsVersion;
  type: "REQUEST_ARTIFACT";
  run_id: string;
  schema: string;
  hash: string;
};

export type WsClientDirectiveSubmitted = {
  v: WsVersion;
  type: "DIRECTIVE_SUBMITTED";
  run_id: string;
  path: string;
};

export type WsClientMessage = WsClientHello | WsClientPause | WsClientRequestArtifact | WsClientDirectiveSubmitted;

export type WsServerMessage =
  | {
      v: WsVersion;
      type: "WELCOME";
      server_time_utc: string;
      mode: OmegaMode;
      run_id: string;
      ledger_path: string;
    }
  | {
      v: WsVersion;
      type: "FULL_SNAPSHOT";
      run_id: string;
      payload: SnapshotPayload;
    }
  | {
      v: WsVersion;
      type: "LEDGER_EVENT";
      line: number;
      event: OmegaLedgerEventV1;
    }
  | {
      v: WsVersion;
      type: "ARTIFACT";
      schema: string;
      hash: string;
      payload: Record<string, unknown> | null;
    }
  | {
      v: WsVersion;
      type: "DIRECTIVE_SUBMITTED";
      run_id: string;
      path: string;
      submitted_at_utc: string;
    }
  | {
      v: WsVersion;
      type: "ERROR";
      code: "RUN_NOT_FOUND" | "INVALID_PATH" | "INTERNAL";
      detail: string;
    };

export type RunKind = "single" | "series";

export type RunInfo = {
  run_id: string;
  kind: RunKind;
  abs_path: string | null;
  members?: Array<{
    tick_u64: number;
    run_id: string;
    abs_path: string;
  }>;
  tick_min_u64?: number;
  tick_max_u64?: number;
  tick_count?: number;
  last_seen_utc: string | null;
  mode: OmegaMode;
};
