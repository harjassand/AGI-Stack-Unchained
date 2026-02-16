import CryptoJS from "crypto-js";

export type CanonValue = null | boolean | number | string | CanonValue[] | { [key: string]: CanonValue };

function canonize(value: unknown): CanonValue {
  if (value === null) {
    return null;
  }
  if (typeof value === "boolean" || typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("NON_FINITE_NUMBER");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => canonize(item));
  }
  if (typeof value === "object") {
    const row = value as Record<string, unknown>;
    const out: Record<string, CanonValue> = {};
    for (const key of Object.keys(row).sort()) {
      out[key] = canonize(row[key]);
    }
    return out;
  }
  throw new Error("UNSUPPORTED_CANON_TYPE");
}

export function canonJson(value: unknown): string {
  return JSON.stringify(canonize(value));
}

function toWordArray(value: string | Uint8Array): CryptoJS.lib.WordArray {
  if (typeof value === "string") {
    return CryptoJS.enc.Utf8.parse(value);
  }
  return CryptoJS.lib.WordArray.create(value as unknown as number[]);
}

export function sha256Hex(value: string | Buffer | Uint8Array): string {
  const bytes = typeof value === "string" ? value : value instanceof Uint8Array ? value : new Uint8Array(value);
  return CryptoJS.SHA256(toWordArray(bytes as string | Uint8Array)).toString(CryptoJS.enc.Hex);
}

export function sha256Prefixed(value: string | Buffer | Uint8Array): string {
  return `sha256:${sha256Hex(value)}`;
}

export function canonHash(value: unknown): string {
  return sha256Prefixed(canonJson(value));
}

export function hashFromPrefixed(hash: string): string {
  if (!hash.startsWith("sha256:")) {
    throw new Error("INVALID_HASH_PREFIX");
  }
  const hex = hash.slice("sha256:".length);
  if (!/^[0-9a-f]{64}$/.test(hex)) {
    throw new Error("INVALID_HASH_HEX");
  }
  return hex;
}
