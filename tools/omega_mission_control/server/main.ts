import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import next from "next";
import { WebSocketServer, type WebSocket } from "ws";

import {
  buildSnapshotPayload,
  compareTickStates,
  discoverRunArtifactsForMembers,
  hashSearch,
  latestSnapshotForRun,
  listDispatchTimeline,
  loadTextFileLimited,
  promotionBundleForDispatch,
  proofFilesForDispatch,
  resolveArtifactBySchemaHash,
  snapshotForRunTick,
} from "./artifacts_v18";
import { LedgerTailCursor } from "./fs_stream_v18";
import { MockGeneratorV18 } from "./mock_generator_v18";
import { type ResolvedRun, resolveRunV18, selectSeriesMember } from "./run_resolve_v18";
import { ledgerPathForRun, scanRunsRootV18, stateRootForRun } from "./run_scan_v18";
import { DISPATCH_DIR_PATTERN, formatSeriesDispatchId, parseSeriesDispatchId } from "./series_dispatch_v18";
import { SecurityError, ensureRealPathUnderRoot, safeResolveUnderRoot, validateRunId } from "./security";
import { encodeServerMessage, parseClientMessage, wsError } from "./ws_protocol_v1";
import { WS_VERSION, type OmegaMode, type SnapshotPayload, type WsServerMessage } from "../lib/types_v18";

const TOOL_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RUNTIME_ROOT = path.join(TOOL_ROOT, "runtime");
const INBOX_ROOT = path.join(RUNTIME_ROOT, "inbox");
const UPLOADS_ROOT = path.join(RUNTIME_ROOT, "uploads");
const MOCK_ROOT = path.join(RUNTIME_ROOT, "mock_runs");
const DEFAULT_REPO_ROOT = path.resolve(TOOL_ROOT, "..", "..");

type AppConfig = {
  mode: OmegaMode;
  runsRootAbs: string;
  repoRootAbs: string;
  enableRepoFile: boolean;
  port: number;
  host: string;
  dev: boolean;
};

type WsConnState = {
  socket: WebSocket;
  runId: string | null;
  runAbs: string | null;
  ledgerPath: string | null;
  cursor: LedgerTailCursor | null;
  paused: boolean;
  pending: WsServerMessage[];
  timer: NodeJS.Timeout;
};

type TickIndexRow = {
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

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const nextToken = argv[i + 1];
    if (!nextToken || nextToken.startsWith("--")) {
      out[key] = true;
      continue;
    }
    out[key] = nextToken;
    i += 1;
  }
  return out;
}

function pickArg(args: Record<string, string | boolean>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const v = args[key];
    if (typeof v === "string" && v.trim().length > 0) {
      return v.trim();
    }
  }
  return undefined;
}

function isDirectoryNoSymlink(abs: string): boolean {
  try {
    const st = fs.lstatSync(abs);
    return st.isDirectory() && !st.isSymbolicLink();
  } catch {
    return false;
  }
}

function parseTruthy(value: string | undefined): boolean {
  if (!value) {
    return false;
  }
  return value === "1" || value.toLowerCase() === "true";
}

function buildConfig(): AppConfig {
  const args = parseArgs(process.argv.slice(2));

  const repoRootRaw = pickArg(args, "repo_root", "repo-root") ?? process.env.OMEGA_MC_REPO_ROOT ?? DEFAULT_REPO_ROOT;
  const repoRootAbs = path.resolve(repoRootRaw);

  const runsOverride = pickArg(args, "runs_root", "runs-root") ?? process.env.OMEGA_MC_RUNS_ROOT;
  const runsRootAbs = path.resolve(runsOverride ?? path.join(repoRootAbs, "runs"));
  const runsRootExists = isDirectoryNoSymlink(runsRootAbs);

  const modeRaw = pickArg(args, "mode") ?? process.env.OMEGA_MC_MODE;
  const mode: OmegaMode = modeRaw === "mock" ? "mock" : modeRaw === "fs" ? "fs" : runsRootExists ? "fs" : "mock";

  const portRaw = pickArg(args, "port") ?? process.env.PORT ?? "3000";
  const port = Number.parseInt(portRaw, 10);
  if (!Number.isFinite(port) || port <= 0 || port > 65535) {
    throw new Error("INVALID_PORT");
  }

  const host = pickArg(args, "host") ?? process.env.HOST ?? "0.0.0.0";
  const dev = !!args.dev || process.env.NODE_ENV !== "production";
  const enableRepoFile = parseTruthy(
    pickArg(args, "enable_repo_file", "enable-repo-file") ?? process.env.OMEGA_MC_ENABLE_REPO_FILE,
  );

  process.env.OMEGA_MC_MODE = mode;
  process.env.OMEGA_MC_RUNS_ROOT = runsRootAbs;
  process.env.OMEGA_MC_REPO_ROOT = repoRootAbs;

  return {
    mode,
    runsRootAbs,
    repoRootAbs,
    enableRepoFile,
    port,
    host,
    dev,
  };
}

function effectiveRunsRoot(config: AppConfig): string {
  return config.mode === "mock" ? MOCK_ROOT : config.runsRootAbs;
}

function json(res: http.ServerResponse, statusCode: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  res.statusCode = statusCode;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(body));
  res.end(body);
}

function text(res: http.ServerResponse, statusCode: number, payload: string): void {
  res.statusCode = statusCode;
  res.setHeader("content-type", "text/plain; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(payload));
  res.end(payload);
}

function badRequest(res: http.ServerResponse, detail: string): void {
  json(res, 400, { error: detail });
}

function internalError(res: http.ServerResponse, detail: string): void {
  json(res, 500, { error: detail });
}

function readBody(req: http.IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let total = 0;
    req.on("data", (chunk) => {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      total += buf.length;
      if (total > 10 * 1024 * 1024) {
        reject(new Error("BODY_TOO_LARGE"));
        req.destroy();
        return;
      }
      chunks.push(buf);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function sendWs(socket: WebSocket, msg: WsServerMessage): void {
  if (socket.readyState !== socket.OPEN) {
    return;
  }
  socket.send(encodeServerMessage(msg));
}

function closeWsWithError(state: WsConnState, code: "RUN_NOT_FOUND" | "INVALID_PATH" | "INTERNAL", detail: string): void {
  sendWs(state.socket, wsError(code, detail));
}

function parseTickQuery(value: string | null): number | undefined | null {
  if (value === null || value.trim().length === 0) {
    return undefined;
  }
  const tick = Number.parseInt(value, 10);
  if (!Number.isFinite(tick) || tick < 0) {
    return null;
  }
  return Math.floor(tick);
}

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

function asBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function runAbsFromResolved(resolved: ResolvedRun, tick?: number): { runAbs: string; memberRunId: string | null; tick_u64: number | null } | null {
  if (resolved.kind === "single") {
    return { runAbs: resolved.runAbs, memberRunId: resolved.runId, tick_u64: null };
  }
  const member = selectSeriesMember(resolved.members, tick);
  if (!member) {
    return null;
  }
  return { runAbs: member.runAbs, memberRunId: member.runId, tick_u64: member.tick_u64 };
}

function buildSeriesSnapshotPayload(
  seriesId: string,
  members: Array<{ tick_u64: number; runId: string; runAbs: string }>,
  tick?: number,
): SnapshotPayload | null {
  const selectedMember = selectSeriesMember(members, tick);
  if (!selectedMember) {
    return null;
  }

  const selectedRow = snapshotForRunTick(selectedMember.runAbs, selectedMember.tick_u64) ?? latestSnapshotForRun(selectedMember.runAbs);
  const selectedTick = selectedRow?.tick_u64;
  const payload = buildSnapshotPayload(selectedMember.runAbs, selectedTick, { include_extras: true });

  const byTickRows = members
    .map((member) => {
      const row = snapshotForRunTick(member.runAbs, member.tick_u64) ?? latestSnapshotForRun(member.runAbs);
      if (!row) {
        return null;
      }
      return {
        tick_u64: row.tick_u64,
        snapshot_hash: row.snapshot_hash,
        snapshot: row.snapshot,
        member_run_id: member.runId,
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null)
    .sort((a, b) => a.tick_u64 - b.tick_u64 || a.member_run_id.localeCompare(b.member_run_id));

  payload.ticks = byTickRows.map((row) => row.tick_u64);
  payload.by_tick = byTickRows;
  payload.series = {
    series_id: seriesId,
    tick_count: members.length,
    tick_min: members[0].tick_u64,
    tick_max: members[members.length - 1].tick_u64,
  };
  const artifactIndex = discoverRunArtifactsForMembers(
    members.map((member) => ({
      run_id: member.runId,
      run_abs: member.runAbs,
      order_u64: member.tick_u64,
    })),
  );
  if (!payload.run_artifacts) {
    payload.run_artifacts = {
      omega_diagnostic_packet_v1: null,
      omega_gate_proof_v1: null,
      omega_preflight_report_v1: null,
      omega_replay_manifest_v1: null,
      artifact_index: artifactIndex,
    };
  } else {
    payload.run_artifacts.artifact_index = artifactIndex;
  }
  return payload;
}

function listDispatchesForResolvedRun(resolved: ResolvedRun): Array<Record<string, unknown>> {
  if (resolved.kind === "single") {
    return listDispatchTimeline(resolved.runAbs, 50);
  }

  const out: Array<Record<string, unknown>> = [];
  for (const member of resolved.members) {
    const rows = listDispatchTimeline(member.runAbs, 200);
    for (const row of rows) {
      const rawDispatchId = asString(row.dispatch_id);
      if (!rawDispatchId || !DISPATCH_DIR_PATTERN.test(rawDispatchId)) {
        continue;
      }
      out.push({
        ...row,
        dispatch_id: formatSeriesDispatchId(member.tick_u64, rawDispatchId),
        member_tick_u64: member.tick_u64,
        member_run_id: member.runId,
      });
    }
  }

  out.sort((a, b) => {
    const aTick = Math.floor(asNumber(a.tick_u64) ?? -1);
    const bTick = Math.floor(asNumber(b.tick_u64) ?? -1);
    if (aTick !== bTick) {
      return bTick - aTick;
    }
    const aId = asString(a.dispatch_id) ?? "";
    const bId = asString(b.dispatch_id) ?? "";
    return bId.localeCompare(aId);
  });
  return out.slice(0, 200);
}

function resolveDispatchTarget(
  resolved: ResolvedRun,
  dispatchId: string,
): { runAbs: string; dispatchDir: string } | "INVALID_DISPATCH_ID" | null {
  if (resolved.kind === "single") {
    if (!DISPATCH_DIR_PATTERN.test(dispatchId)) {
      return "INVALID_DISPATCH_ID";
    }
    return {
      runAbs: resolved.runAbs,
      dispatchDir: dispatchId,
    };
  }

  const parsed = parseSeriesDispatchId(dispatchId);
  if (!parsed) {
    return "INVALID_DISPATCH_ID";
  }
  const member = resolved.members.find((row) => row.tick_u64 === parsed.tick_u64);
  if (!member) {
    return null;
  }
  return {
    runAbs: member.runAbs,
    dispatchDir: parsed.dispatch_dir,
  };
}

function buildTickIndexRows(resolved: ResolvedRun): TickIndexRow[] {
  const targets =
    resolved.kind === "single"
      ? [{ runAbs: resolved.runAbs, runId: resolved.runId, tick_u64: undefined as number | undefined }]
      : resolved.members.map((member) => ({ runAbs: member.runAbs, runId: member.runId, tick_u64: member.tick_u64 }));

  const out: TickIndexRow[] = [];

  for (const target of targets) {
    const snapshotTick = target.tick_u64;
    const payload = buildSnapshotPayload(target.runAbs, snapshotTick, { include_extras: false });
    const latestSnapshot = asRecord(payload.latest_snapshot);
    const tick_u64 = Math.floor(asNumber(latestSnapshot?.tick_u64) ?? snapshotTick ?? 0);

    const decision = asRecord(payload.artifacts.omega_decision_plan_v1);
    const dispatchReceipt = asRecord(payload.artifacts.omega_dispatch_receipt_v1);
    const subverifier = asRecord(payload.artifacts.omega_subverifier_receipt_v1);
    const promotion = asRecord(payload.artifacts.omega_promotion_receipt_v1);
    const activation = asRecord(payload.artifacts.omega_activation_receipt_v1);

    const timeline = listDispatchTimeline(target.runAbs, 6);
    const dispatchRow =
      timeline.find((row) => Math.floor(asNumber(row.tick_u64) ?? -1) === tick_u64) ??
      timeline[0] ??
      null;
    const dispatchRowRec = asRecord(dispatchRow);

    const subResult = asRecord(subverifier?.result);
    const promotionResult = asRecord(promotion?.result);

    const subStatus = asString(subResult?.status) ?? asString(dispatchRowRec?.subverifier_status);
    const subReason = asString(subResult?.reason_code) ?? asString(dispatchRowRec?.subverifier_reason_code);
    const promotionStatus = asString(promotionResult?.status) ?? asString(dispatchRowRec?.promotion_status);
    const promotionReason = asString(promotionResult?.reason_code) ?? asString(dispatchRowRec?.promotion_reason_code);
    const activationSuccess = asBool(activation?.pass) ?? asBool(dispatchRowRec?.activation_pass);
    const activationReason =
      asString((activation as Record<string, unknown> | null)?.reason_code) ??
      asString((activation as Record<string, unknown> | null)?.cause) ??
      asString(dispatchRowRec?.activation_reason_code);

    let failingStage = "OK";
    if (!dispatchReceipt && !dispatchRowRec) {
      failingStage = "DISPATCH";
    } else if (subStatus && subStatus !== "VALID") {
      failingStage = "SUBVERIFIER";
    } else if (promotionStatus && promotionStatus !== "PROMOTED") {
      failingStage = "PROMOTION";
    } else if (activationSuccess !== true) {
      failingStage = "ACTIVATION";
    }

    let reasonCode: string | null = null;
    if (failingStage === "SUBVERIFIER") {
      reasonCode = subReason ?? null;
    } else if (failingStage === "PROMOTION") {
      reasonCode = promotionReason ?? null;
    } else if (failingStage === "ACTIVATION") {
      reasonCode = activationReason ?? (activationSuccess === false ? "ACTIVATION_FAILED" : null);
    } else if (failingStage === "DISPATCH") {
      const rc = asNumber(dispatchRowRec?.return_code);
      if (rc !== null && rc !== 0) {
        reasonCode = `RETURN_CODE_${Math.floor(rc)}`;
      }
    }

    const selectedMetric = asString(decision?.runaway_selected_metric_id);
    const escalation = Math.floor(asNumber(decision?.runaway_escalation_level_u64) ?? 0);
    const plannedCampaign = asString(decision?.campaign_id);
    const suggestedNextAction =
      selectedMetric !== null
        ? `metric=${selectedMetric}; escalation=${escalation}; campaign=${plannedCampaign ?? "n/a"}`
        : null;

    out.push({
      tick_u64,
      action_kind: asString(decision?.action_kind),
      campaign_id: asString(decision?.campaign_id) ?? asString(dispatchReceipt?.campaign_id) ?? asString(dispatchRowRec?.campaign_id),
      capability_id: asString(decision?.capability_id) ?? asString(dispatchReceipt?.capability_id) ?? asString(dispatchRowRec?.capability_id),
      subverifier_status: subStatus ?? null,
      subverifier_reason_code: subReason ?? null,
      promotion_status: promotionStatus ?? null,
      promotion_reason_code: promotionReason ?? null,
      activation_success: activationSuccess,
      failing_stage: failingStage,
      reason_code: reasonCode,
      suggested_next_action: suggestedNextAction,
      dispatch_id: asString(dispatchRowRec?.dispatch_id),
      member_run_id: target.runId,
      stdout_rel: asString(dispatchRowRec?.stdout_rel),
      stderr_rel: asString(dispatchRowRec?.stderr_rel),
      verifier_stdout_rel: asString(dispatchRowRec?.verifier_stdout_rel),
      verifier_stderr_rel: asString(dispatchRowRec?.verifier_stderr_rel),
    });
  }

  out.sort((a, b) => a.tick_u64 - b.tick_u64 || (a.member_run_id ?? "").localeCompare(b.member_run_id ?? ""));
  if (resolved.kind === "single") {
    return out.slice(-1);
  }
  return out;
}

async function main(): Promise<void> {
  const config = buildConfig();

  fs.mkdirSync(INBOX_ROOT, { recursive: true });
  fs.mkdirSync(UPLOADS_ROOT, { recursive: true });
  fs.mkdirSync(MOCK_ROOT, { recursive: true });

  let mockGenerator: MockGeneratorV18 | null = null;
  if (config.mode === "mock") {
    mockGenerator = new MockGeneratorV18({ runtimeRootAbs: RUNTIME_ROOT });
    mockGenerator.start();
  }

  const app = next({
    dev: config.dev,
    dir: TOOL_ROOT,
    hostname: config.host,
    port: config.port,
  });
  const handleNext = app.getRequestHandler();
  await app.prepare();

  const server = http.createServer(async (req, res) => {
    if (!req.url || !req.method) {
      badRequest(res, "INVALID_REQUEST");
      return;
    }
    const method = req.method.toUpperCase();
    const url = new URL(req.url, `http://${req.headers.host ?? `127.0.0.1:${config.port}`}`);
    const pathname = url.pathname;

    const runsRootAbs = effectiveRunsRoot(config);

    try {
      if (method === "GET" && pathname === "/api/v1/runs") {
        const includeTicks = url.searchParams.get("include_ticks") === "1";
        const runs = scanRunsRootV18(runsRootAbs, config.mode, { include_ticks: includeTicks });
        json(res, 200, { runs });
        return;
      }

      const snapshotMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/snapshot$/);
      if (method === "GET" && snapshotMatch) {
        const runId = validateRunId(decodeURIComponent(snapshotMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }

        const tick = parseTickQuery(url.searchParams.get("tick"));
        if (tick === null) {
          badRequest(res, "INVALID_TICK");
          return;
        }

        if (resolved.kind === "single") {
          const payload = buildSnapshotPayload(resolved.runAbs, tick);
          json(res, 200, { run_id: runId, payload });
          return;
        }

        const payload = buildSeriesSnapshotPayload(resolved.seriesId, resolved.members, tick);
        if (!payload) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        json(res, 200, { run_id: runId, payload });
        return;
      }

      const fileMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/file$/);
      if (method === "GET" && fileMatch) {
        const runId = validateRunId(decodeURIComponent(fileMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }

        const tick = parseTickQuery(url.searchParams.get("tick"));
        if (tick === null) {
          badRequest(res, "INVALID_TICK");
          return;
        }
        const selected = runAbsFromResolved(resolved, tick);
        if (!selected) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }

        const rel = url.searchParams.get("rel") ?? "";
        const targetAbs = safeResolveUnderRoot(selected.runAbs, rel);
        if (!fs.existsSync(targetAbs)) {
          json(res, 404, { error: "NOT_FOUND" });
          return;
        }
        const safeAbs = ensureRealPathUnderRoot(selected.runAbs, targetAbs);
        const content = loadTextFileLimited(safeAbs);
        text(res, 200, content);
        return;
      }

      const hashSearchMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/hash-search$/);
      if (method === "GET" && hashSearchMatch) {
        const runId = validateRunId(decodeURIComponent(hashSearchMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const tick = parseTickQuery(url.searchParams.get("tick"));
        if (tick === null) {
          badRequest(res, "INVALID_TICK");
          return;
        }
        const selected = runAbsFromResolved(resolved, tick);
        if (!selected) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const hash = url.searchParams.get("hash") ?? "";
        json(res, 200, hashSearch(selected.runAbs, hash));
        return;
      }

      const compareMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/compare-ticks$/);
      if (method === "GET" && compareMatch) {
        const runId = validateRunId(decodeURIComponent(compareMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const selected = runAbsFromResolved(resolved, undefined);
        if (!selected) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const a = Number.parseInt(url.searchParams.get("a") ?? "", 10);
        const b = Number.parseInt(url.searchParams.get("b") ?? "", 10);
        if (!Number.isFinite(a) || !Number.isFinite(b)) {
          badRequest(res, "INVALID_TICK");
          return;
        }
        json(res, 200, compareTickStates(selected.runAbs, a, b));
        return;
      }

      const dispatchesMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/dispatches$/);
      if (method === "GET" && dispatchesMatch) {
        const runId = validateRunId(decodeURIComponent(dispatchesMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        json(res, 200, { run_id: runId, dispatches: listDispatchesForResolvedRun(resolved) });
        return;
      }

      const tickIndexMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/tick-index$/);
      if (method === "GET" && tickIndexMatch) {
        const runId = validateRunId(decodeURIComponent(tickIndexMatch[1]));
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        json(res, 200, { run_id: runId, rows: buildTickIndexRows(resolved) });
        return;
      }

      const promoMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/dispatch\/([^/]+)\/promotion-bundle$/);
      if (method === "GET" && promoMatch) {
        const runId = validateRunId(decodeURIComponent(promoMatch[1]));
        const dispatchId = decodeURIComponent(promoMatch[2]);
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const target = resolveDispatchTarget(resolved, dispatchId);
        if (target === "INVALID_DISPATCH_ID") {
          badRequest(res, "INVALID_DISPATCH_ID");
          return;
        }
        if (!target) {
          json(res, 404, { error: "DISPATCH_NOT_FOUND" });
          return;
        }
        const payload = promotionBundleForDispatch(target.runAbs, target.dispatchDir);
        json(res, 200, { run_id: runId, dispatch_id: dispatchId, payload });
        return;
      }

      const proofsMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/dispatch\/([^/]+)\/proofs$/);
      if (method === "GET" && proofsMatch) {
        const runId = validateRunId(decodeURIComponent(proofsMatch[1]));
        const dispatchId = decodeURIComponent(proofsMatch[2]);
        const resolved = resolveRunV18(runsRootAbs, runId);
        if (!resolved) {
          json(res, 404, { error: "RUN_NOT_FOUND" });
          return;
        }
        const target = resolveDispatchTarget(resolved, dispatchId);
        if (target === "INVALID_DISPATCH_ID") {
          badRequest(res, "INVALID_DISPATCH_ID");
          return;
        }
        if (!target) {
          json(res, 404, { error: "DISPATCH_NOT_FOUND" });
          return;
        }
        json(res, 200, { run_id: runId, dispatch_id: dispatchId, files: proofFilesForDispatch(target.runAbs, target.dispatchDir) });
        return;
      }

      const repoFileMatch = pathname.match(/^\/api\/v1\/runs\/([^/]+)\/repo-file$/);
      if (method === "GET" && repoFileMatch) {
        validateRunId(decodeURIComponent(repoFileMatch[1]));
        if (!config.enableRepoFile) {
          json(res, 403, { error: "REPO_FILE_DISABLED" });
          return;
        }
        const rel = url.searchParams.get("rel") ?? "";
        const targetAbs = safeResolveUnderRoot(config.repoRootAbs, rel);
        if (!fs.existsSync(targetAbs)) {
          json(res, 404, { error: "NOT_FOUND" });
          return;
        }
        const safeAbs = ensureRealPathUnderRoot(config.repoRootAbs, targetAbs);
        const content = loadTextFileLimited(safeAbs);
        text(res, 200, content);
        return;
      }

      if (method === "POST" && pathname === "/api/v1/directives") {
        const body = JSON.parse((await readBody(req)).toString("utf-8")) as { directive?: string };
        const directive = typeof body.directive === "string" ? body.directive.trim() : "";
        if (!directive) {
          badRequest(res, "DIRECTIVE_REQUIRED");
          return;
        }
        const now = new Date();
        const iso = now.toISOString().replace(/[:-]/g, "").replace(/\.\d{3}Z$/, "Z");
        const digest = crypto.createHash("sha256").update(directive).digest("hex");
        const fileName = `${iso}_${digest.slice(0, 16)}.omega_command_v1.json`;
        const payload = {
          schema_version: "omega_command_v1",
          submitted_at_utc: now.toISOString(),
          directive,
        };
        const outAbs = path.join(INBOX_ROOT, fileName);
        fs.writeFileSync(outAbs, JSON.stringify(payload), "utf-8");

        const rel = path.relative(TOOL_ROOT, outAbs).replaceAll(path.sep, "/");
        const msg: WsServerMessage = {
          v: WS_VERSION,
          type: "DIRECTIVE_SUBMITTED",
          run_id: "runtime",
          path: rel,
          submitted_at_utc: now.toISOString(),
        };
        for (const conn of connections) {
          sendWs(conn.socket, msg);
        }

        json(res, 200, { ok: true, path: rel, submitted_at_utc: now.toISOString() });
        return;
      }

      if (method === "POST" && pathname === "/api/v1/uploads") {
        const body = JSON.parse((await readBody(req)).toString("utf-8")) as {
          files?: Array<{ name?: string; data_base64?: string }>;
        };
        const files = Array.isArray(body.files) ? body.files : [];
        if (files.length === 0) {
          badRequest(res, "FILES_REQUIRED");
          return;
        }

        const uploadHash = crypto
          .createHash("sha256")
          .update(JSON.stringify(files.map((f) => ({ name: f.name, len: f.data_base64?.length ?? 0 }))))
          .digest("hex");
        const uploadDir = path.join(UPLOADS_ROOT, uploadHash);
        fs.mkdirSync(uploadDir, { recursive: true });

        const written: string[] = [];
        for (const file of files) {
          const name = path.basename((file.name ?? "upload.bin").replaceAll("\\", "/"));
          const data = typeof file.data_base64 === "string" ? Buffer.from(file.data_base64, "base64") : Buffer.alloc(0);
          const outAbs = path.join(uploadDir, name);
          fs.writeFileSync(outAbs, data);
          written.push(path.relative(TOOL_ROOT, outAbs).replaceAll(path.sep, "/"));
        }

        json(res, 200, { ok: true, upload_id: uploadHash, files: written });
        return;
      }

      if (method === "GET" && pathname === "/api/v1/uploads") {
        const out: Array<{ upload_id: string; files: string[] }> = [];
        if (fs.existsSync(UPLOADS_ROOT)) {
          for (const entry of fs.readdirSync(UPLOADS_ROOT, { withFileTypes: true })) {
            if (!entry.isDirectory()) {
              continue;
            }
            const dir = path.join(UPLOADS_ROOT, entry.name);
            const files = fs
              .readdirSync(dir, { withFileTypes: true })
              .filter((f) => f.isFile())
              .map((f) => f.name)
              .sort();
            out.push({ upload_id: entry.name, files });
          }
        }
        out.sort((a, b) => a.upload_id.localeCompare(b.upload_id));
        json(res, 200, { uploads: out });
        return;
      }

      await handleNext(req, res);
    } catch (err) {
      if (err instanceof SecurityError) {
        badRequest(res, err.code);
        return;
      }
      const detail = err instanceof Error ? err.message : "INTERNAL";
      internalError(res, detail);
    }
  });

  const wss = new WebSocketServer({ noServer: true });
  const connections = new Set<WsConnState>();

  server.on("upgrade", (req, socket, head) => {
    const url = new URL(req.url ?? "", `http://${req.headers.host ?? `127.0.0.1:${config.port}`}`);
    if (url.pathname !== "/ws") {
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, req);
    });
  });

  wss.on("connection", (socket) => {
    const state: WsConnState = {
      socket,
      runId: null,
      runAbs: null,
      ledgerPath: null,
      cursor: null,
      paused: false,
      pending: [],
      timer: setInterval(() => {
        if (!state.cursor || !state.ledgerPath) {
          return;
        }
        try {
          const rows = state.cursor.poll(state.ledgerPath);
          for (const row of rows) {
            const msg: WsServerMessage = {
              v: WS_VERSION,
              type: "LEDGER_EVENT",
              line: row.line,
              event: row.event,
            };
            if (state.paused) {
              state.pending.push(msg);
            } else {
              sendWs(socket, msg);
            }
          }
        } catch (err) {
          closeWsWithError(state, "INTERNAL", err instanceof Error ? err.message : "INTERNAL");
        }
      }, 500),
    };
    connections.add(state);

    socket.on("message", (data) => {
      const msg = parseClientMessage(data.toString());
      if (!msg) {
        closeWsWithError(state, "INVALID_PATH", "INVALID_PROTOCOL_MESSAGE");
        return;
      }

      const runsRootAbs = effectiveRunsRoot(config);

      if (msg.type === "HELLO") {
        try {
          const runId = validateRunId(msg.run_id);
          const resolved = resolveRunV18(runsRootAbs, runId);
          if (!resolved) {
            closeWsWithError(state, "RUN_NOT_FOUND", "RUN_NOT_FOUND");
            return;
          }
          const selected = runAbsFromResolved(resolved, undefined);
          if (!selected) {
            closeWsWithError(state, "RUN_NOT_FOUND", "RUN_NOT_FOUND");
            return;
          }

          state.runId = runId;
          state.runAbs = selected.runAbs;
          state.ledgerPath = ledgerPathForRun(selected.runAbs);
          state.cursor = new LedgerTailCursor(Number.isFinite(msg.from_line) ? msg.from_line : 0);

          sendWs(socket, {
            v: WS_VERSION,
            type: "WELCOME",
            server_time_utc: new Date().toISOString(),
            mode: config.mode,
            run_id: runId,
            ledger_path: state.ledgerPath,
          });

          if (msg.send_full_snapshot) {
            const payload =
              resolved.kind === "single"
                ? buildSnapshotPayload(selected.runAbs)
                : buildSeriesSnapshotPayload(resolved.seriesId, resolved.members) ?? buildSnapshotPayload(selected.runAbs);
            sendWs(socket, {
              v: WS_VERSION,
              type: "FULL_SNAPSHOT",
              run_id: runId,
              payload,
            });
          }

          const rows = state.cursor.poll(state.ledgerPath);
          for (const row of rows) {
            sendWs(socket, {
              v: WS_VERSION,
              type: "LEDGER_EVENT",
              line: row.line,
              event: row.event,
            });
          }
        } catch (err) {
          if (err instanceof SecurityError) {
            closeWsWithError(state, "INVALID_PATH", err.code);
            return;
          }
          closeWsWithError(state, "INTERNAL", err instanceof Error ? err.message : "INTERNAL");
        }
        return;
      }

      if (msg.type === "SET_PAUSE") {
        state.paused = !!msg.paused;
        if (!state.paused && state.pending.length > 0) {
          for (const row of state.pending.splice(0)) {
            sendWs(socket, row);
          }
        }
        return;
      }

      if (msg.type === "REQUEST_ARTIFACT") {
        try {
          const runId = validateRunId(msg.run_id);
          const resolved = resolveRunV18(runsRootAbs, runId);
          if (!resolved) {
            closeWsWithError(state, "RUN_NOT_FOUND", "RUN_NOT_FOUND");
            return;
          }
          const selected = runAbsFromResolved(resolved, undefined);
          if (!selected) {
            closeWsWithError(state, "RUN_NOT_FOUND", "RUN_NOT_FOUND");
            return;
          }

          const stateRoot = stateRootForRun(selected.runAbs);
          const artifact = resolveArtifactBySchemaHash(stateRoot, msg.schema, msg.hash);
          sendWs(socket, {
            v: WS_VERSION,
            type: "ARTIFACT",
            schema: msg.schema,
            hash: msg.hash,
            payload: artifact?.payload ?? null,
          });
        } catch (err) {
          if (err instanceof SecurityError) {
            closeWsWithError(state, "INVALID_PATH", err.code);
            return;
          }
          closeWsWithError(state, "INTERNAL", err instanceof Error ? err.message : "INTERNAL");
        }
        return;
      }

      if (msg.type === "DIRECTIVE_SUBMITTED") {
        const event: WsServerMessage = {
          v: WS_VERSION,
          type: "DIRECTIVE_SUBMITTED",
          run_id: msg.run_id,
          path: msg.path,
          submitted_at_utc: new Date().toISOString(),
        };
        for (const conn of connections) {
          sendWs(conn.socket, event);
        }
      }
    });

    socket.on("close", () => {
      clearInterval(state.timer);
      connections.delete(state);
    });

    socket.on("error", () => {
      clearInterval(state.timer);
      connections.delete(state);
    });
  });

  server.listen(config.port, config.host, () => {
    const runsRoot = effectiveRunsRoot(config);
    const mockInfo = mockGenerator ? ` mock_run=${mockGenerator.runId}` : "";
    // eslint-disable-next-line no-console
    console.log(`omega_mission_control listening on http://${config.host}:${config.port} mode=${config.mode} runs_root=${runsRoot}${mockInfo}`);
  });
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exitCode = 1;
});
