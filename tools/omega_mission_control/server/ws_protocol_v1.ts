import { WS_VERSION, type WsClientMessage, type WsServerMessage } from "../lib/types_v18";

export function isWsV1(value: unknown): value is { v: string; type: string } {
  return typeof value === "object" && value !== null && "v" in value && "type" in value;
}

export function parseClientMessage(raw: string): WsClientMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isWsV1(parsed) || parsed.v !== WS_VERSION || typeof parsed.type !== "string") {
    return null;
  }
  return parsed as WsClientMessage;
}

export function encodeServerMessage(message: WsServerMessage): string {
  return JSON.stringify(message);
}

export function wsError(code: "RUN_NOT_FOUND" | "INVALID_PATH" | "INTERNAL", detail: string): WsServerMessage {
  return {
    v: WS_VERSION,
    type: "ERROR",
    code,
    detail,
  };
}
