import { describe, expect, it } from "vitest";
import { SecurityError, safeResolveUnderRoot } from "../security";

describe("path traversal guard", () => {
  it("rejects /file rel traversal like ../.. with INVALID_PATH", () => {
    expect(() => safeResolveUnderRoot("/tmp/omega-runs", "../..")).toThrow(SecurityError);
    try {
      safeResolveUnderRoot("/tmp/omega-runs", "../..");
    } catch (err) {
      expect(err).toBeInstanceOf(SecurityError);
      expect((err as SecurityError).code).toBe("INVALID_PATH");
    }
  });
});
