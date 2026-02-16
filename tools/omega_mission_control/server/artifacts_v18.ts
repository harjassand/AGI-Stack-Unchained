import fs from "node:fs";
import path from "node:path";
import { canonHash, hashFromPrefixed, sha256Prefixed } from "../lib/canon_sha256";
import type { OmegaLedgerEventV1, RunArtifactIndexEntryV18, SnapshotPayload } from "../lib/types_v18";
import { configRootForRun, ledgerPathForRun, stateRootForRun } from "./run_scan_v18";

type JsonObj = Record<string, unknown>;

export type TickSnapshotRow = {
  tick_u64: number;
  snapshot_hash: string;
  snapshot: JsonObj;
  pathAbs: string;
};

const TWO_MB = 2 * 1024 * 1024;

const DIRECT_HASH_MAP: Record<string, { dir: string; suffix: string }> = {
  omega_state_v1: { dir: "state", suffix: "omega_state_v1.json" },
  omega_observation_report_v1: { dir: "observations", suffix: "omega_observation_report_v1.json" },
  omega_issue_bundle_v1: { dir: "issues", suffix: "omega_issue_bundle_v1.json" },
  omega_decision_plan_v1: { dir: "decisions", suffix: "omega_decision_plan_v1.json" },
  omega_tick_snapshot_v1: { dir: "snapshot", suffix: "omega_tick_snapshot_v1.json" },
  omega_trace_hash_chain_v1: { dir: "ledger", suffix: "omega_trace_hash_chain_v1.json" },
};

const RUN_ARTIFACT_FILENAMES = [
  "OMEGA_DIAGNOSTIC_PACKET_v1.json",
  "OMEGA_GATE_PROOF_v1.json",
  "OMEGA_PREFLIGHT_REPORT_v1.json",
  "OMEGA_REPLAY_MANIFEST_v1.json",
];

export function readJsonFile(pathAbs: string): JsonObj | null {
  if (!fs.existsSync(pathAbs) || !fs.statSync(pathAbs).isFile()) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(pathAbs, "utf-8")) as JsonObj;
  } catch {
    return null;
  }
}

function asObject(value: unknown): JsonObj | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as JsonObj;
}

function readGeAuditReport(runAbs: string): JsonObj | null {
  const directPath = path.join(runAbs, "GE_AUDIT_REPORT_v1.json");
  const direct = readJsonFile(directPath);
  if (direct) {
    return direct;
  }

  const overnightReport = readJsonFile(path.join(runAbs, "OMEGA_OVERNIGHT_REPORT_v1.json"));
  const geSh1 = asObject(overnightReport?.ge_sh1);
  const auditPath = geSh1 && typeof geSh1.audit_report_json === "string" ? geSh1.audit_report_json : "";
  if (!auditPath) {
    return null;
  }
  const auditAbs = path.isAbsolute(auditPath) ? auditPath : path.resolve(runAbs, auditPath);
  return readJsonFile(auditAbs);
}

function readJsonlObjects(pathAbs: string): JsonObj[] {
  if (!fs.existsSync(pathAbs) || !fs.statSync(pathAbs).isFile()) {
    return [];
  }
  const out: JsonObj[] = [];
  const lines = fs.readFileSync(pathAbs, "utf-8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      continue;
    }
    try {
      const payload = JSON.parse(line);
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        out.push(payload as JsonObj);
      }
    } catch {
      // Skip malformed lines.
    }
  }
  return out;
}

function readLlmRouterPlan(runAbs: string): JsonObj | null {
  return readJsonFile(path.join(runAbs, "OMEGA_LLM_ROUTER_PLAN_v1.json"));
}

function readLlmToolTrace(runAbs: string): JsonObj[] {
  return readJsonlObjects(path.join(runAbs, "OMEGA_LLM_TOOL_TRACE_v1.jsonl"));
}

function runIdFromAbs(runAbs: string): string {
  return path.basename(runAbs);
}

function readRunArtifact(runAbs: string, filename: string): JsonObj | null {
  return readJsonFile(path.join(runAbs, filename));
}

type RunArtifactMember = {
  run_id: string;
  run_abs: string;
  order_u64: number;
};

export function discoverRunArtifactsForMembers(members: RunArtifactMember[]): RunArtifactIndexEntryV18[] {
  const rows: RunArtifactIndexEntryV18[] = [];
  const orderedMembers = [...members].sort((a, b) => b.order_u64 - a.order_u64 || a.run_id.localeCompare(b.run_id));
  const sortedFilenames = [...RUN_ARTIFACT_FILENAMES].sort((a, b) => a.localeCompare(b));
  for (const member of orderedMembers) {
    for (const filename of sortedFilenames) {
      const abs = path.join(member.run_abs, filename);
      if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
        continue;
      }
      rows.push({
        run_id: member.run_id,
        filename,
        path_rel: path.relative(member.run_abs, abs).replaceAll(path.sep, "/"),
      });
    }
  }
  return rows;
}

function asShaHex(hash: string): string | null {
  try {
    return hashFromPrefixed(hash);
  } catch {
    return null;
  }
}

function readHashedFile(stateRoot: string, dir: string, suffix: string, hash: string): { pathAbs: string; payload: JsonObj } | null {
  const hex = asShaHex(hash);
  if (!hex) {
    return null;
  }
  const target = path.join(stateRoot, dir, `sha256_${hex}.${suffix}`);
  const payload = readJsonFile(target);
  if (!payload) {
    return null;
  }
  return { pathAbs: target, payload };
}

function latestHashedFilePayload(stateRoot: string, dir: string, suffix: string): JsonObj | null {
  const root = path.join(stateRoot, dir);
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    return null;
  }

  const files = fs
    .readdirSync(root)
    .filter((name) => new RegExp(`^sha256_[0-9a-f]{64}\\.${suffix.replace(/\./g, "\\.")}$`).test(name))
    .map((name) => path.join(root, name));
  if (files.length === 0) {
    return null;
  }

  files.sort((a, b) => {
    try {
      return fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs || b.localeCompare(a);
    } catch {
      return b.localeCompare(a);
    }
  });
  return readJsonFile(files[0]);
}

function readDispatchReceiptByHash(stateRoot: string, hash: string): { pathAbs: string; payload: JsonObj } | null {
  const hex = asShaHex(hash);
  if (!hex) {
    return null;
  }
  const dispatchRoot = path.join(stateRoot, "dispatch");
  if (!fs.existsSync(dispatchRoot)) {
    return null;
  }
  const fileName = `sha256_${hex}.omega_dispatch_receipt_v1.json`;
  const dirs = fs.readdirSync(dispatchRoot, { withFileTypes: true }).filter((d) => d.isDirectory());
  const hits: string[] = [];
  for (const dirent of dirs) {
    const candidate = path.join(dispatchRoot, dirent.name, fileName);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      hits.push(candidate);
    }
  }
  if (hits.length !== 1) {
    return null;
  }
  const payload = readJsonFile(hits[0]);
  if (!payload) {
    return null;
  }
  return { pathAbs: hits[0], payload };
}

function scanRecursiveForFilename(root: string, targetName: string): string[] {
  const out: string[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
      } else if (entry.isFile() && entry.name === targetName) {
        out.push(abs);
      }
    }
  }
  out.sort();
  return out;
}

function scanRecursiveFiles(root: string): string[] {
  const out: string[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
      } else if (entry.isFile()) {
        out.push(abs);
      }
    }
  }
  out.sort();
  return out;
}

function readNestedDispatchReceiptByHash(
  stateRoot: string,
  hash: string,
  suffix: "omega_subverifier_receipt_v1.json" | "omega_promotion_receipt_v1.json" | "omega_activation_receipt_v1.json" | "omega_rollback_receipt_v1.json",
): { pathAbs: string; payload: JsonObj } | null {
  const hex = asShaHex(hash);
  if (!hex) {
    return null;
  }
  const dispatchRoot = path.join(stateRoot, "dispatch");
  if (!fs.existsSync(dispatchRoot)) {
    return null;
  }
  const fileName = `sha256_${hex}.${suffix}`;
  const hits = scanRecursiveForFilename(dispatchRoot, fileName);
  if (hits.length !== 1) {
    return null;
  }
  const payload = readJsonFile(hits[0]);
  if (!payload) {
    return null;
  }
  return { pathAbs: hits[0], payload };
}

export function resolveArtifactBySchemaHash(stateRoot: string, schema: string, hash: string): { pathAbs: string; payload: JsonObj } | null {
  const direct = DIRECT_HASH_MAP[schema];
  if (direct) {
    return readHashedFile(stateRoot, direct.dir, direct.suffix, hash);
  }
  if (schema === "omega_dispatch_receipt_v1") {
    return readDispatchReceiptByHash(stateRoot, hash);
  }
  if (schema === "omega_subverifier_receipt_v1") {
    return readNestedDispatchReceiptByHash(stateRoot, hash, "omega_subverifier_receipt_v1.json");
  }
  if (schema === "omega_promotion_receipt_v1") {
    return readNestedDispatchReceiptByHash(stateRoot, hash, "omega_promotion_receipt_v1.json");
  }
  if (schema === "omega_activation_receipt_v1") {
    return readNestedDispatchReceiptByHash(stateRoot, hash, "omega_activation_receipt_v1.json");
  }
  if (schema === "omega_rollback_receipt_v1") {
    return readNestedDispatchReceiptByHash(stateRoot, hash, "omega_rollback_receipt_v1.json");
  }
  return null;
}

function snapshotFiles(stateRoot: string): string[] {
  const dir = path.join(stateRoot, "snapshot");
  if (!fs.existsSync(dir)) {
    return [];
  }
  return fs
    .readdirSync(dir)
    .filter((name) => /^sha256_[0-9a-f]{64}\.omega_tick_snapshot_v1\.json$/.test(name))
    .map((name) => path.join(dir, name))
    .sort();
}

function runawayStateFiles(stateRoot: string): string[] {
  const dir = path.join(stateRoot, "runaway");
  if (!fs.existsSync(dir)) {
    return [];
  }
  return fs
    .readdirSync(dir)
    .filter((name) => /^sha256_[0-9a-f]{64}\.omega_runaway_state_v1\.json$/.test(name))
    .map((name) => path.join(dir, name))
    .sort();
}

function hashFromHashedFilename(filePath: string): string | null {
  const match = path.basename(filePath).match(/^sha256_([0-9a-f]{64})\./);
  if (!match) {
    return null;
  }
  return `sha256:${match[1]}`;
}

function asTickNumber(value: unknown): number {
  if (typeof value !== "number") {
    return -1;
  }
  return Math.floor(value);
}

function listSnapshotsWithTicks(stateRoot: string): TickSnapshotRow[] {
  const out: TickSnapshotRow[] = [];
  for (const filePath of snapshotFiles(stateRoot)) {
    const payload = readJsonFile(filePath);
    if (!payload) {
      continue;
    }
    const hash = hashFromHashedFilename(filePath);
    if (!hash) {
      continue;
    }
    const tick = asTickNumber(payload.tick_u64);
    out.push({ tick_u64: tick, snapshot_hash: hash, snapshot: payload, pathAbs: filePath });
  }
  out.sort((a, b) => (a.tick_u64 - b.tick_u64) || a.pathAbs.localeCompare(b.pathAbs));
  return out;
}

function listRunawayStatesWithTicks(stateRoot: string): Array<{ tick_u64: number; payload: JsonObj; pathAbs: string }> {
  const out: Array<{ tick_u64: number; payload: JsonObj; pathAbs: string }> = [];
  for (const filePath of runawayStateFiles(stateRoot)) {
    const payload = readJsonFile(filePath);
    if (!payload) {
      continue;
    }
    const tick = asTickNumber(payload.tick_u64);
    out.push({ tick_u64: tick, payload, pathAbs: filePath });
  }
  out.sort((a, b) => (a.tick_u64 - b.tick_u64) || a.pathAbs.localeCompare(b.pathAbs));
  return out;
}

function runawayStateForTick(stateRoot: string, tick?: number): JsonObj | null {
  const rows = listRunawayStatesWithTicks(stateRoot);
  if (rows.length === 0) {
    return null;
  }
  if (typeof tick !== "number") {
    return rows[rows.length - 1].payload;
  }
  let selected: JsonObj | null = null;
  for (const row of rows) {
    if (row.tick_u64 <= tick) {
      selected = row.payload;
      continue;
    }
    break;
  }
  return selected;
}

function latestSnapshotRow(stateRoot: string): TickSnapshotRow | null {
  const rows = listSnapshotsWithTicks(stateRoot);
  if (rows.length === 0) {
    return null;
  }
  return rows[rows.length - 1];
}

function snapshotForTick(stateRoot: string, tick: number): TickSnapshotRow | null {
  const rows = listSnapshotsWithTicks(stateRoot);
  const found = rows.find((row) => row.tick_u64 === tick);
  return found ?? null;
}

export function latestSnapshotForRun(runAbs: string): TickSnapshotRow | null {
  return latestSnapshotRow(stateRootForRun(runAbs));
}

export function snapshotForRunTick(runAbs: string, tick: number): TickSnapshotRow | null {
  return snapshotForTick(stateRootForRun(runAbs), tick);
}

function nullableHash(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  return /^sha256:[0-9a-f]{64}$/.test(value) ? value : null;
}

function loadConfig(configRoot: string, rel: string): JsonObj | null {
  return readJsonFile(path.join(configRoot, rel));
}

function maybeResolve(stateRoot: string, schema: string, hash: unknown): JsonObj | null {
  const h = nullableHash(hash);
  if (!h) {
    return null;
  }
  return resolveArtifactBySchemaHash(stateRoot, schema, h)?.payload ?? null;
}

function readLedger(ledgerPath: string): OmegaLedgerEventV1[] {
  if (!fs.existsSync(ledgerPath) || !fs.statSync(ledgerPath).isFile()) {
    return [];
  }
  const rows: OmegaLedgerEventV1[] = [];
  const lines = fs.readFileSync(ledgerPath, "utf-8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      continue;
    }
    try {
      rows.push(JSON.parse(line) as OmegaLedgerEventV1);
    } catch {
      // skip malformed entries
    }
  }
  return rows;
}

export function listDispatchTimeline(runAbs: string, limit = 50): Array<Record<string, unknown>> {
  const stateRoot = stateRootForRun(runAbs);
  const dispatchRoot = path.join(stateRoot, "dispatch");
  if (!fs.existsSync(dispatchRoot) || !fs.statSync(dispatchRoot).isDirectory()) {
    return [];
  }

  const out: Array<Record<string, unknown>> = [];
  const dispatchDirs = fs
    .readdirSync(dispatchRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(dispatchRoot, entry.name))
    .sort((a, b) => {
      try {
        return fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs;
      } catch {
        return b.localeCompare(a);
      }
    });

  for (const dir of dispatchDirs) {
    const receiptPath = fs
      .readdirSync(dir)
      .find((name) => /^sha256_[0-9a-f]{64}\.omega_dispatch_receipt_v1\.json$/.test(name));
    if (!receiptPath) {
      continue;
    }
    const dispatchReceiptAbs = path.join(dir, receiptPath);
    const dispatchReceipt = readJsonFile(dispatchReceiptAbs);
    if (!dispatchReceipt) {
      continue;
    }

    const dispatchId = path.basename(dir);
    const dispatchHash = hashFromHashedFilename(dispatchReceiptAbs);

    const allFiles = scanRecursiveFiles(dir);
    const subverifierPath = allFiles.find((abs) => /\.omega_subverifier_receipt_v1\.json$/.test(abs));
    const promotionPath = allFiles.find((abs) => /\.omega_promotion_receipt_v1\.json$/.test(abs));
    const activationPath = allFiles.find((abs) => /\.omega_activation_receipt_v1\.json$/.test(abs));
    const rollbackPath = allFiles.find((abs) => /\.omega_rollback_receipt_v1\.json$/.test(abs));

    const subverifier = subverifierPath ? readJsonFile(subverifierPath) : null;
    const promotion = promotionPath ? readJsonFile(promotionPath) : null;
    const activation = activationPath ? readJsonFile(activationPath) : null;
    const rollback = rollbackPath ? readJsonFile(rollbackPath) : null;

    const subrunRootRel =
      (dispatchReceipt.subrun as JsonObj | undefined)?.subrun_root_rel &&
      String((dispatchReceipt.subrun as JsonObj).subrun_root_rel);

    out.push({
      dispatch_id: dispatchId,
      tick_u64: dispatchReceipt.tick_u64,
      campaign_id: dispatchReceipt.campaign_id,
      capability_id: dispatchReceipt.capability_id,
      return_code: dispatchReceipt.return_code,
      dispatch_hash: dispatchHash,
      subverifier_status: (subverifier?.result as JsonObj | undefined)?.status ?? null,
      subverifier_reason_code: (subverifier?.result as JsonObj | undefined)?.reason_code ?? null,
      promotion_status: (promotion?.result as JsonObj | undefined)?.status ?? null,
      promotion_reason_code: (promotion?.result as JsonObj | undefined)?.reason_code ?? null,
      activation_pass: activation?.pass ?? null,
      activation_reason_code:
        (activation as JsonObj | null)?.reason_code ??
        (activation as JsonObj | null)?.cause ??
        (activation as JsonObj | null)?.error_code ??
        null,
      rollback_cause: rollback?.cause ?? null,
      dispatch_rel: path.relative(runAbs, dispatchReceiptAbs).replaceAll(path.sep, "/"),
      stdout_rel: path.relative(runAbs, path.join(dir, "stdout.log")).replaceAll(path.sep, "/"),
      stderr_rel: path.relative(runAbs, path.join(dir, "stderr.log")).replaceAll(path.sep, "/"),
      verifier_stdout_rel: path.relative(runAbs, path.join(dir, "verifier", "stdout.log")).replaceAll(path.sep, "/"),
      verifier_stderr_rel: path.relative(runAbs, path.join(dir, "verifier", "stderr.log")).replaceAll(path.sep, "/"),
      subrun_root_rel: subrunRootRel ?? null,
      promotion_receipt: promotion,
      dispatch_receipt: dispatchReceipt,
      subverifier_receipt: subverifier,
      activation_receipt: activation,
      rollback_receipt: rollback,
    });

    if (out.length >= limit) {
      break;
    }
  }

  return out;
}

export function extractTouchedPaths(bundle: unknown): string[] {
  const out: string[] = [];

  const walk = (value: unknown): void => {
    if (Array.isArray(value)) {
      for (const row of value) {
        walk(row);
      }
      return;
    }
    if (!value || typeof value !== "object") {
      return;
    }
    const record = value as Record<string, unknown>;
    for (const [key, item] of Object.entries(record)) {
      if (["path", "file", "relpath", "target_rel"].includes(key) && typeof item === "string") {
        out.push(item);
      }
      if (["paths", "files", "touched_paths", "patch_paths"].includes(key) && Array.isArray(item)) {
        for (const row of item) {
          if (typeof row === "string") {
            out.push(row);
          }
        }
      }
      walk(item);
    }
  };

  walk(bundle);
  const cleaned = out.filter((row) => row.length > 0 && !row.startsWith("/") && !row.includes("\\") && !row.split("/").includes(".."));
  return Array.from(new Set(cleaned)).sort();
}

function findPromotionBundleByHash(stateRoot: string, promotionBundleHash: string | null): { pathAbs: string; payload: JsonObj; touched_paths: string[] } | null {
  if (!promotionBundleHash || !/^sha256:[0-9a-f]{64}$/.test(promotionBundleHash)) {
    return null;
  }
  const hex = promotionBundleHash.split(":", 2)[1];
  const subrunsDir = path.join(stateRoot, "subruns");
  if (!fs.existsSync(subrunsDir) || !fs.statSync(subrunsDir).isDirectory()) {
    return null;
  }
  const matches: string[] = [];
  const stack = [subrunsDir];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
      } else if (entry.isFile() && new RegExp(`^sha256_${hex}\\..+\\.json$`).test(entry.name)) {
        matches.push(abs);
      }
    }
  }
  if (matches.length === 0) {
    return null;
  }
  matches.sort();
  const payload = readJsonFile(matches[0]);
  if (!payload) {
    return null;
  }
  return {
    pathAbs: matches[0],
    payload,
    touched_paths: extractTouchedPaths(payload),
  };
}

export function promotionBundleForDispatch(runAbs: string, dispatchId: string): Record<string, unknown> | null {
  const stateRoot = stateRootForRun(runAbs);
  const dispatchDir = path.join(stateRoot, "dispatch", dispatchId);
  if (!fs.existsSync(dispatchDir) || !fs.statSync(dispatchDir).isDirectory()) {
    return null;
  }
  const promotionReceiptPath = scanRecursiveFiles(dispatchDir)
    .find((abs) => /\.omega_promotion_receipt_v1\.json$/.test(abs));
  if (!promotionReceiptPath) {
    return null;
  }
  const promotionReceipt = readJsonFile(promotionReceiptPath);
  if (!promotionReceipt) {
    return null;
  }
  const bundleHash = typeof promotionReceipt.promotion_bundle_hash === "string" ? promotionReceipt.promotion_bundle_hash : null;
  const bundle = findPromotionBundleByHash(stateRoot, bundleHash);

  return {
    promotion_receipt: promotionReceipt,
    promotion_receipt_rel: path.relative(runAbs, promotionReceiptPath).replaceAll(path.sep, "/"),
    bundle_hash: bundleHash,
    bundle_payload: bundle?.payload ?? null,
    bundle_rel: bundle ? path.relative(runAbs, bundle.pathAbs).replaceAll(path.sep, "/") : null,
    touched_paths: bundle?.touched_paths ?? [],
  };
}

export function proofFilesForDispatch(runAbs: string, dispatchId: string): Array<{ rel: string; content: string }> {
  const stateRoot = stateRootForRun(runAbs);
  const dispatchDir = path.join(stateRoot, "dispatch", dispatchId);
  if (!fs.existsSync(dispatchDir) || !fs.statSync(dispatchDir).isDirectory()) {
    return [];
  }
  const dispatchReceiptFile = fs
    .readdirSync(dispatchDir)
    .find((name) => /^sha256_[0-9a-f]{64}\.omega_dispatch_receipt_v1\.json$/.test(name));
  if (!dispatchReceiptFile) {
    return [];
  }
  const dispatchReceipt = readJsonFile(path.join(dispatchDir, dispatchReceiptFile));
  const subrun = dispatchReceipt?.subrun as JsonObj | undefined;
  const subrunRootRel = typeof subrun?.subrun_root_rel === "string" ? subrun.subrun_root_rel : null;
  const stateDirRel = typeof subrun?.state_dir_rel === "string" ? subrun.state_dir_rel : null;
  if (!subrunRootRel || !stateDirRel) {
    return [];
  }
  const targetRoot = path.join(stateRoot, subrunRootRel, stateDirRel);
  if (!fs.existsSync(targetRoot) || !fs.statSync(targetRoot).isDirectory()) {
    return [];
  }

  const out: Array<{ rel: string; content: string }> = [];
  for (const file of scanRecursiveFiles(targetRoot)) {
    if (!file.endsWith(".lean")) {
      continue;
    }
    try {
      const content = loadTextFileLimited(file);
      out.push({
        rel: path.relative(targetRoot, file).replaceAll(path.sep, "/"),
        content,
      });
    } catch {
      // Skip unreadable/large files.
    }
  }
  out.sort((a, b) => a.rel.localeCompare(b.rel));
  return out;
}

export function loadTextFileLimited(pathAbs: string): string {
  const stat = fs.statSync(pathAbs);
  if (!stat.isFile()) {
    throw new Error("NOT_A_FILE");
  }
  if (stat.size > TWO_MB) {
    throw new Error("FILE_TOO_LARGE");
  }
  const buf = fs.readFileSync(pathAbs);
  if (buf.includes(0)) {
    throw new Error("BINARY_FILE");
  }
  return buf.toString("utf-8");
}

function readStateBySnapshot(stateRoot: string, snapshot: JsonObj): SnapshotPayload["artifacts"] {
  return {
    omega_state_v1: maybeResolve(stateRoot, "omega_state_v1", snapshot.state_hash),
    omega_observation_report_v1: maybeResolve(stateRoot, "omega_observation_report_v1", snapshot.observation_report_hash),
    omega_issue_bundle_v1: maybeResolve(stateRoot, "omega_issue_bundle_v1", snapshot.issue_bundle_hash),
    omega_decision_plan_v1: maybeResolve(stateRoot, "omega_decision_plan_v1", snapshot.decision_plan_hash),
    omega_dispatch_receipt_v1: maybeResolve(stateRoot, "omega_dispatch_receipt_v1", snapshot.dispatch_receipt_hash),
    omega_subverifier_receipt_v1: maybeResolve(stateRoot, "omega_subverifier_receipt_v1", snapshot.subverifier_receipt_hash),
    omega_promotion_receipt_v1: maybeResolve(stateRoot, "omega_promotion_receipt_v1", snapshot.promotion_receipt_hash),
    omega_activation_receipt_v1: maybeResolve(stateRoot, "omega_activation_receipt_v1", snapshot.activation_receipt_hash),
    omega_rollback_receipt_v1: maybeResolve(stateRoot, "omega_rollback_receipt_v1", snapshot.rollback_receipt_hash),
    omega_trace_hash_chain_v1: maybeResolve(stateRoot, "omega_trace_hash_chain_v1", snapshot.trace_hash_chain_hash),
    omega_runaway_state_v1: runawayStateForTick(stateRoot, asTickNumber(snapshot.tick_u64)),
  };
}

function readLatestInProgressArtifacts(stateRoot: string): SnapshotPayload["artifacts"] {
  return {
    omega_state_v1: latestHashedFilePayload(stateRoot, "state", "omega_state_v1.json"),
    omega_observation_report_v1: latestHashedFilePayload(stateRoot, "observations", "omega_observation_report_v1.json"),
    omega_issue_bundle_v1: latestHashedFilePayload(stateRoot, "issues", "omega_issue_bundle_v1.json"),
    omega_decision_plan_v1: latestHashedFilePayload(stateRoot, "decisions", "omega_decision_plan_v1.json"),
    omega_dispatch_receipt_v1: null,
    omega_subverifier_receipt_v1: null,
    omega_promotion_receipt_v1: null,
    omega_activation_receipt_v1: null,
    omega_rollback_receipt_v1: null,
    omega_trace_hash_chain_v1: latestHashedFilePayload(stateRoot, "ledger", "omega_trace_hash_chain_v1.json"),
    omega_runaway_state_v1: runawayStateForTick(stateRoot),
  };
}

export function buildSnapshotPayload(runAbs: string, tick?: number, opts: { include_extras?: boolean } = {}): SnapshotPayload {
  const stateRoot = stateRootForRun(runAbs);
  const configRoot = configRootForRun(runAbs);

  const selected = typeof tick === "number" ? snapshotForTick(stateRoot, tick) : latestSnapshotRow(stateRoot);
  const byTickRows = listSnapshotsWithTicks(stateRoot);

  const latest = selected?.snapshot ?? null;
  const artifacts = latest ? readStateBySnapshot(stateRoot, latest) : readLatestInProgressArtifacts(stateRoot);
  const runId = runIdFromAbs(runAbs);
  const runArtifactIndex = discoverRunArtifactsForMembers([
    {
      run_id: runId,
      run_abs: runAbs,
      order_u64: Math.max(0, asTickNumber(latest?.tick_u64)),
    },
  ]);

  const payload: SnapshotPayload = {
    latest_snapshot: latest,
    snapshot_hash: selected?.snapshot_hash ?? null,
    artifacts,
    config: {
      omega_budgets_v1: loadConfig(configRoot, "omega_budgets_v1.json"),
      omega_capability_registry_v2: loadConfig(configRoot, "omega_capability_registry_v2.json"),
      omega_goal_queue_v1: loadConfig(configRoot, path.join("goals", "omega_goal_queue_v1.json")),
      omega_objectives_v1: loadConfig(configRoot, "omega_objectives_v1.json"),
      omega_runaway_config_v1: loadConfig(configRoot, "omega_runaway_config_v1.json"),
    },
    run_artifacts: {
      omega_diagnostic_packet_v1: readRunArtifact(runAbs, "OMEGA_DIAGNOSTIC_PACKET_v1.json") as any,
      omega_gate_proof_v1: readRunArtifact(runAbs, "OMEGA_GATE_PROOF_v1.json") as any,
      omega_preflight_report_v1: readRunArtifact(runAbs, "OMEGA_PREFLIGHT_REPORT_v1.json") as any,
      omega_replay_manifest_v1: readRunArtifact(runAbs, "OMEGA_REPLAY_MANIFEST_v1.json") as any,
      artifact_index: runArtifactIndex,
    },
    ticks: byTickRows.map((row) => row.tick_u64),
    by_tick: byTickRows.map((row) => ({ tick_u64: row.tick_u64, snapshot_hash: row.snapshot_hash, snapshot: row.snapshot })),
    runaway_state_history: listRunawayStatesWithTicks(stateRoot).map((row) => row.payload),
  };

  if (opts.include_extras === false) {
    return payload;
  }

  const extras: Record<string, unknown> = {
    dispatch_timeline: listDispatchTimeline(runAbs, 50),
    ledger_tail: readLedger(ledgerPathForRun(runAbs)).slice(-400),
    ge_audit_report_v1: readGeAuditReport(runAbs),
    llm_router_plan_v1: readLlmRouterPlan(runAbs),
    llm_tool_trace_v1: readLlmToolTrace(runAbs),
  };

  return Object.assign(payload, extras);
}

export function hashSearch(runAbs: string, hash: string): Record<string, unknown> {
  const hex = asShaHex(hash);
  if (!hex) {
    return { hash, matches: [] };
  }

  const targetPattern = new RegExp(`sha256_${hex}`);
  const matches: string[] = [];
  const stack = [runAbs];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const abs = path.join(cur, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
      } else if (entry.isFile() && targetPattern.test(entry.name)) {
        matches.push(path.relative(runAbs, abs).replaceAll(path.sep, "/"));
      }
    }
  }

  matches.sort();
  return {
    hash,
    matches,
  };
}

function diffJson(a: unknown, b: unknown, prefix = ""): Array<{ path: string; before: unknown; after: unknown }> {
  const out: Array<{ path: string; before: unknown; after: unknown }> = [];

  if (Object.is(a, b)) {
    return out;
  }

  const aObj = a !== null && typeof a === "object";
  const bObj = b !== null && typeof b === "object";
  if (!aObj || !bObj || Array.isArray(a) !== Array.isArray(b)) {
    out.push({ path: prefix || "$", before: a, after: b });
    return out;
  }

  if (Array.isArray(a) && Array.isArray(b)) {
    const max = Math.max(a.length, b.length);
    for (let i = 0; i < max; i += 1) {
      out.push(...diffJson(a[i], b[i], `${prefix}[${i}]`));
    }
    return out;
  }

  const aRec = a as Record<string, unknown>;
  const bRec = b as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(aRec), ...Object.keys(bRec)])).sort();
  for (const key of keys) {
    const child = prefix ? `${prefix}.${key}` : key;
    out.push(...diffJson(aRec[key], bRec[key], child));
  }
  return out;
}

export function compareTickStates(runAbs: string, aTick: number, bTick: number): Record<string, unknown> {
  const stateRoot = stateRootForRun(runAbs);
  const aSnapshot = snapshotForTick(stateRoot, aTick);
  const bSnapshot = snapshotForTick(stateRoot, bTick);
  if (!aSnapshot || !bSnapshot) {
    return {
      a_tick: aTick,
      b_tick: bTick,
      found: false,
      diff: [],
    };
  }

  const aState = maybeResolve(stateRoot, "omega_state_v1", aSnapshot.snapshot.state_hash);
  const bState = maybeResolve(stateRoot, "omega_state_v1", bSnapshot.snapshot.state_hash);

  return {
    a_tick: aTick,
    b_tick: bTick,
    found: true,
    a_state_hash: aSnapshot.snapshot.state_hash,
    b_state_hash: bSnapshot.snapshot.state_hash,
    diff: diffJson(aState, bState),
  };
}

export function validateTraceChain(trace: JsonObj | null): { pass: boolean; h0: string | null; expected: string | null; computed: string | null; mismatch_at: number | null } {
  if (!trace) {
    return { pass: false, h0: null, expected: null, computed: null, mismatch_at: null };
  }
  const h0 = typeof trace.H0 === "string" ? trace.H0 : null;
  const expected = typeof trace.H_final === "string" ? trace.H_final : null;
  const hashes = Array.isArray(trace.artifact_hashes) ? trace.artifact_hashes.filter((x): x is string => typeof x === "string") : [];
  if (!h0 || !expected) {
    return { pass: false, h0, expected, computed: null, mismatch_at: null };
  }
  let head = h0;
  let mismatch: number | null = null;
  for (let i = 0; i < hashes.length; i += 1) {
    head = canonHash({ schema_version: "omega_trace_step_v1", prev: head, artifact_hash: hashes[i] });
    if (mismatch === null && head !== expected && i === hashes.length - 1) {
      mismatch = i;
    }
  }
  return {
    pass: head === expected,
    h0,
    expected,
    computed: head,
    mismatch_at: mismatch,
  };
}

export function validateLedgerChain(events: OmegaLedgerEventV1[]): { pass: boolean; first_error_line: number | null; reason: string | null } {
  let prev: string | null = null;
  for (let i = 0; i < events.length; i += 1) {
    const row = events[i];
    if (row.prev_event_id !== prev) {
      return { pass: false, first_error_line: i, reason: "prev_event_id_mismatch" };
    }
    const candidate = {
      schema_version: row.schema_version,
      tick_u64: row.tick_u64,
      event_type: row.event_type,
      artifact_hash: row.artifact_hash,
      prev_event_id: row.prev_event_id,
    };
    const eventId = sha256Prefixed(Buffer.from(JSON.stringify(sortKeys(candidate))));
    if (eventId !== row.event_id) {
      return { pass: false, first_error_line: i, reason: "event_id_hash_mismatch" };
    }
    prev = row.event_id;
  }
  return { pass: true, first_error_line: null, reason: null };
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((row) => sortKeys(row));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  const inRec = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(inRec).sort()) {
    out[key] = sortKeys(inRec[key]);
  }
  return out;
}

export function computeLedgerEventId(event: Omit<OmegaLedgerEventV1, "event_id">): string {
  return canonHash(event);
}

export function buildLedgerEventsFromArtifacts(
  tick: number,
  artifactHashes: {
    state: string;
    observation: string;
    issue: string;
    decision: string;
    dispatch: string | null;
    subverifier: string | null;
    promotion: string | null;
    activation: string | null;
    rollback: string | null;
    snapshot: string;
    safe_halt?: string | null;
  },
  prevEventId: string | null,
): { events: OmegaLedgerEventV1[]; prevEventId: string } {
  const rows: Array<{ event_type: OmegaLedgerEventV1["event_type"]; artifact_hash: string | null }> = [
    { event_type: "STATE", artifact_hash: artifactHashes.state },
    { event_type: "OBSERVATION", artifact_hash: artifactHashes.observation },
    { event_type: "ISSUE", artifact_hash: artifactHashes.issue },
    { event_type: "DECISION", artifact_hash: artifactHashes.decision },
    { event_type: "DISPATCH", artifact_hash: artifactHashes.dispatch },
    { event_type: "SUBVERIFIER", artifact_hash: artifactHashes.subverifier },
    { event_type: "PROMOTION", artifact_hash: artifactHashes.promotion },
    { event_type: "ACTIVATION", artifact_hash: artifactHashes.activation },
    { event_type: "ROLLBACK", artifact_hash: artifactHashes.rollback },
    { event_type: "SNAPSHOT", artifact_hash: artifactHashes.snapshot },
    { event_type: "SAFE_HALT", artifact_hash: artifactHashes.safe_halt ?? null },
  ];

  const out: OmegaLedgerEventV1[] = [];
  let prev = prevEventId;
  for (const row of rows) {
    if (!row.artifact_hash) {
      continue;
    }
    const eventNoId = {
      schema_version: "omega_ledger_event_v1" as const,
      tick_u64: tick,
      event_type: row.event_type,
      artifact_hash: row.artifact_hash,
      prev_event_id: prev,
    };
    const event: OmegaLedgerEventV1 = {
      ...eventNoId,
      event_id: computeLedgerEventId(eventNoId),
    };
    out.push(event);
    prev = event.event_id;
  }
  return {
    events: out,
    prevEventId: prev ?? "",
  };
}

export function appendLedgerEvents(ledgerPath: string, events: OmegaLedgerEventV1[]): void {
  if (events.length === 0) {
    return;
  }
  const lines = events.map((row) => JSON.stringify(row)).join("\n") + "\n";
  fs.appendFileSync(ledgerPath, lines, "utf-8");
}

export function writeHashedArtifact(
  outDir: string,
  schemaName: string,
  payload: JsonObj,
  idField?: string,
): { pathAbs: string; payload: JsonObj; hash: string } {
  fs.mkdirSync(outDir, { recursive: true });
  const obj: JsonObj = { ...payload };
  if (idField) {
    const noId = { ...obj };
    delete noId[idField];
    obj[idField] = canonHash(noId);
  }
  const hash = canonHash(obj);
  const hex = hash.split(":", 2)[1];
  const filePath = path.join(outDir, `sha256_${hex}.${schemaName}.json`);
  fs.writeFileSync(filePath, JSON.stringify(sortKeys(obj)), "utf-8");
  return {
    pathAbs: filePath,
    payload: obj,
    hash,
  };
}
