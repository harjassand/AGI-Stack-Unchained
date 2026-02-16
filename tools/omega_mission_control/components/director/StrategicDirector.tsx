"use client";

import { useEffect, useMemo, useState } from "react";
import { submitDirective, uploadDataset } from "../../lib/api";

type StrategicDirectorProps = {
  mode: "mock" | "fs";
  manualIntervention: boolean;
  setManualIntervention: (next: boolean) => void;
  halted: boolean;
  setHalted: (next: boolean) => void;
  goalQueue: any;
  directiveHistory: Array<{ submitted_at_utc: string; path: string }>;
  tick: number;
};

export default function StrategicDirector({
  mode,
  manualIntervention,
  setManualIntervention,
  halted,
  setHalted,
  goalQueue,
  directiveHistory,
  tick,
}: StrategicDirectorProps) {
  const [directive, setDirective] = useState("");
  const [directiveResult, setDirectiveResult] = useState<string>("");
  const [haltConfirm, setHaltConfirm] = useState("");
  const [uploadResult, setUploadResult] = useState<string>("");
  const [uploads, setUploads] = useState<Array<{ upload_id: string; files: string[] }>>([]);

  const handleFiles = async (files: FileList | null): Promise<void> => {
    if (!files || files.length === 0) {
      return;
    }
    try {
      const result = await uploadDataset(files);
      setUploadResult(`Uploaded ${Array.isArray(result.files) ? result.files.length : 0} files to ${String(result.upload_id ?? "n/a")}`);
    } catch (err) {
      setUploadResult(err instanceof Error ? err.message : "upload failed");
    }
  };

  const curiosity = useMemo(() => {
    if (mode === "mock") {
      return [
        `Investigate optimizer drift around tick ${Math.max(1, tick - 1)}`,
        "Re-balance metasearch cost ratio",
        "Collect additional proof traces for VAL branch",
      ];
    }
    const rows = Array.isArray(goalQueue?.goals) ? (goalQueue.goals as Array<Record<string, unknown>>) : [];
    return rows
      .filter((row) => row?.status === "PENDING" || row?.status === "QUEUED")
      .map((row) => `${String(row.goal_id)}: ${String(row.status)}`);
  }, [mode, goalQueue, tick]);

  useEffect(() => {
    let active = true;
    const loadUploads = async () => {
      try {
        const res = await fetch("/api/v1/uploads", { cache: "no-store" });
        if (!res.ok) {
          return;
        }
        const payload = (await res.json()) as { uploads?: Array<{ upload_id: string; files: string[] }> };
        if (active) {
          setUploads(Array.isArray(payload.uploads) ? payload.uploads : []);
        }
      } catch {
        // Ignore polling errors.
      }
    };
    void loadUploads();
    const timer = setInterval(() => void loadUploads(), 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Manual Intervention Mode</h3>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              style={{ width: 18, height: 18 }}
              type="checkbox"
              checked={manualIntervention}
              onChange={(e) => setManualIntervention(e.target.checked)}
            />
            Enable write actions (directive submission and upload actions)
          </label>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Mission Injection Console</h3>
          <textarea rows={5} value={directive} onChange={(e) => setDirective(e.target.value)} placeholder="Directive" />
          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button
              className="btn primary"
              type="button"
              disabled={!manualIntervention || !directive.trim()}
              onClick={async () => {
                try {
                  const result = await submitDirective(directive.trim());
                  setDirectiveResult(`Submitted: ${String(result.path ?? "unknown")}`);
                  setDirective("");
                } catch (err) {
                  setDirectiveResult(err instanceof Error ? err.message : "failed");
                }
              }}
            >
              Submit Directive
            </button>
            <span style={{ fontSize: 12, color: "var(--ink-muted)", alignSelf: "center" }}>
              writes to `tools/omega_mission_control/runtime/inbox/`
            </span>
          </div>
          {directiveResult && <p style={{ marginBottom: 0 }}>{directiveResult}</p>}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Dataset Ingestion</h3>
          <input
            type="file"
            multiple
            disabled={!manualIntervention}
            onChange={(e) => {
              void handleFiles(e.currentTarget.files);
            }}
          />
          <div
            className="card"
            style={{ marginTop: 8, borderStyle: "dashed", textAlign: "center", color: "var(--ink-muted)" }}
            onDragOver={(e) => {
              e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (!manualIntervention) {
                return;
              }
              void handleFiles(e.dataTransfer.files);
            }}
          >
            Drag and drop dataset files here
          </div>
          {uploadResult && <p>{uploadResult}</p>}
          <p style={{ marginBottom: 0, color: "var(--ink-muted)", fontSize: 12 }}>
            Uploads stored under `tools/omega_mission_control/runtime/uploads/&lt;sha&gt;/...`
          </p>
          <h4>Dataset Inventory</h4>
          {uploads.length === 0 && <p style={{ marginBottom: 0, color: "var(--ink-muted)" }}>No uploaded datasets yet.</p>}
          {uploads.length > 0 && (
            <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
              {uploads.slice().reverse().map((row) => (
                <li key={row.upload_id}>
                  {row.upload_id} ({row.files.length} files)
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0, color: "var(--danger)" }}>Big Red Button (SAFE_HALT)</h3>
          <p style={{ marginTop: 0, color: "var(--ink-muted)", fontSize: 13 }}>
            UI-only in v18.0: stops dashboard stream and marks local session halted.
          </p>
          <input value={haltConfirm} onChange={(e) => setHaltConfirm(e.target.value)} placeholder="type SAFE_HALT" />
          <button
            className="btn danger"
            style={{ marginTop: 8 }}
            type="button"
            disabled={!manualIntervention || haltConfirm !== "SAFE_HALT" || halted}
            onClick={() => setHalted(true)}
          >
            Confirm SAFE_HALT
          </button>
          {halted && <p style={{ color: "var(--danger)", marginBottom: 0 }}>Local session halted.</p>}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Curiosity Queue</h3>
          {curiosity.length === 0 && <p style={{ color: "var(--ink-muted)" }}>Queue empty.</p>}
          {curiosity.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {curiosity.map((row: string) => (
                <li key={row}>{row}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Directive History</h3>
          {directiveHistory.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No directives submitted this session.</p>}
          {directiveHistory.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {directiveHistory.slice(-20).reverse().map((row) => (
                <li key={`${row.submitted_at_utc}_${row.path}`}>
                  {row.submitted_at_utc} - {row.path}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
