import { describe, expect, it } from "vitest";
import { SecurityError, safeResolveRunSubPath, validateRunId, validateSafeRelPath } from "../../server/security";

describe("security", () => {
  it("accepts valid run_id", () => {
    expect(validateRunId("rsi_omega_daemon_v18_0_tick_0001")).toBe("rsi_omega_daemon_v18_0_tick_0001");
  });

  it("rejects invalid run_id", () => {
    expect(() => validateRunId("../../etc/passwd")).toThrow(SecurityError);
  });

  it("rejects traversal and absolute path", () => {
    expect(() => validateSafeRelPath("../x")).toThrow(SecurityError);
    expect(() => validateSafeRelPath("/abs/path")).toThrow(SecurityError);
    expect(() => validateSafeRelPath("foo\\bar")).toThrow(SecurityError);
  });

  it("resolves safe run sub path under root", () => {
    const p = safeResolveRunSubPath("/tmp/runs", "run_1", "a/b/c.txt");
    expect(p).toContain("/tmp/runs/run_1/a/b/c.txt");
  });
});
