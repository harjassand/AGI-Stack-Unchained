"use client";

import { useMemo } from "react";
import { canonJson } from "../../lib/canon_sha256";

type JsonBlockProps = {
  title: string;
  value: unknown;
  canon?: boolean;
};

export default function JsonBlock({ title, value, canon = false }: JsonBlockProps) {
  const text = useMemo(() => {
    if (value === null || value === undefined) {
      return "null";
    }
    try {
      if (canon) {
        return canonJson(value);
      }
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value, canon]);

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <strong>{title}</strong>
        <button
          className="btn"
          onClick={() => {
            void navigator.clipboard.writeText(text);
          }}
          type="button"
        >
          Copy {canon ? "canonical JSON" : "JSON"}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}
