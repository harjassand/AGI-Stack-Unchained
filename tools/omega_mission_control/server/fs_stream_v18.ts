import fs from "node:fs";
import type { OmegaLedgerEventV1 } from "../lib/types_v18";

export type LedgerLine = {
  line: number;
  event: OmegaLedgerEventV1;
};

export function readLedgerFromOffset(ledgerPath: string, fromLine: number): LedgerLine[] {
  if (!fs.existsSync(ledgerPath) || !fs.statSync(ledgerPath).isFile()) {
    return [];
  }
  let content = "";
  try {
    content = fs.readFileSync(ledgerPath, "utf-8");
  } catch {
    return [];
  }
  const lines = content.split(/\r?\n/);
  const out: LedgerLine[] = [];
  for (let i = Math.max(0, fromLine); i < lines.length; i += 1) {
    const raw = lines[i]?.trim();
    if (!raw) {
      continue;
    }
    try {
      const event = JSON.parse(raw) as OmegaLedgerEventV1;
      out.push({ line: i, event });
    } catch {
      // fail-closed on malformed line by skipping output.
    }
  }
  return out;
}

export class LedgerTailCursor {
  private line: number;

  constructor(fromLine: number) {
    this.line = Math.max(0, fromLine);
  }

  poll(ledgerPath: string): LedgerLine[] {
    const rows = readLedgerFromOffset(ledgerPath, this.line);
    if (rows.length > 0) {
      this.line = rows[rows.length - 1].line + 1;
    }
    return rows;
  }

  setLine(line: number): void {
    this.line = Math.max(0, line);
  }

  getLine(): number {
    return this.line;
  }
}
