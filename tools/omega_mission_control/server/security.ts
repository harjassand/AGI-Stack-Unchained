import fs from "node:fs";
import path from "node:path";

export const RUN_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;

export class SecurityError extends Error {
  code: "INVALID_RUN_ID" | "INVALID_PATH" | "PATH_TRAVERSAL_DETECTED";

  constructor(code: "INVALID_RUN_ID" | "INVALID_PATH" | "PATH_TRAVERSAL_DETECTED", message?: string) {
    super(message ?? code);
    this.code = code;
  }
}

export function validateRunId(runId: string): string {
  if (typeof runId !== "string" || !RUN_ID_PATTERN.test(runId)) {
    throw new SecurityError("INVALID_RUN_ID");
  }
  return runId;
}

export function validateSafeRelPath(relPath: string): string {
  if (typeof relPath !== "string") {
    throw new SecurityError("INVALID_PATH");
  }
  if (relPath.length === 0) {
    return relPath;
  }
  if (relPath.includes("\x00") || relPath.includes("\\")) {
    throw new SecurityError("INVALID_PATH");
  }
  if (path.isAbsolute(relPath) || relPath.startsWith("/")) {
    throw new SecurityError("INVALID_PATH");
  }
  for (const part of relPath.split("/")) {
    if (part === "..") {
      throw new SecurityError("INVALID_PATH");
    }
  }
  return relPath;
}

export function safeResolveRunPath(runsRootAbs: string, runId: string): string {
  const validatedRun = validateRunId(runId);
  const root = path.resolve(runsRootAbs);
  const target = path.resolve(root, validatedRun);
  if (!target.startsWith(`${root}${path.sep}`) && target !== root) {
    throw new SecurityError("PATH_TRAVERSAL_DETECTED");
  }
  return target;
}

export function safeResolveRunSubPath(runsRootAbs: string, runId: string, relPath: string): string {
  validateSafeRelPath(relPath);
  const runAbs = safeResolveRunPath(runsRootAbs, runId);
  const target = path.resolve(runAbs, relPath);
  if (!target.startsWith(`${runAbs}${path.sep}`) && target !== runAbs) {
    throw new SecurityError("PATH_TRAVERSAL_DETECTED");
  }
  return target;
}

export function safeResolveUnderRoot(rootAbs: string, relPath: string): string {
  validateSafeRelPath(relPath);
  const root = path.resolve(rootAbs);
  const target = path.resolve(root, relPath);
  if (!target.startsWith(`${root}${path.sep}`) && target !== root) {
    throw new SecurityError("PATH_TRAVERSAL_DETECTED");
  }
  return target;
}

export function ensureRealPathUnderRoot(rootAbs: string, targetAbs: string): string {
  let rootReal = "";
  let targetReal = "";
  try {
    rootReal = fs.realpathSync(rootAbs);
    targetReal = fs.realpathSync(targetAbs);
  } catch {
    throw new SecurityError("INVALID_PATH");
  }
  if (!targetReal.startsWith(`${rootReal}${path.sep}`) && targetReal !== rootReal) {
    throw new SecurityError("PATH_TRAVERSAL_DETECTED");
  }
  return targetReal;
}
