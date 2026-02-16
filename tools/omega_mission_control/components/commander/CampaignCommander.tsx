"use client";

import { createTwoFilesPatch } from "diff";
import { useEffect, useMemo, useState } from "react";
import { fetchTextFile } from "../../lib/api";
import JsonBlock from "../common/JsonBlock";

type CampaignCommanderProps = {
  runId: string;
  dispatches: Array<Record<string, any>>;
};

type LogTab = "dispatch_stdout" | "dispatch_stderr" | "verifier_stdout" | "verifier_stderr";

async function fetchJson(url: string): Promise<any> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

export default function CampaignCommander({ runId, dispatches }: CampaignCommanderProps) {
  const [selectedDispatchId, setSelectedDispatchId] = useState<string | null>(dispatches[0]?.dispatch_id ?? null);
  const [logTab, setLogTab] = useState<LogTab>("dispatch_stdout");
  const [logText, setLogText] = useState<string>("");
  const [promoBundle, setPromoBundle] = useState<any>(null);
  const [diffs, setDiffs] = useState<Array<{ path: string; text: string }>>([]);
  const [proofs, setProofs] = useState<Array<{ rel: string; content: string }>>([]);
  const [proofOpenRel, setProofOpenRel] = useState<string | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [repoDiffDisabled, setRepoDiffDisabled] = useState(false);

  const selected = useMemo(
    () => dispatches.find((row) => row.dispatch_id === selectedDispatchId) ?? dispatches[0] ?? null,
    [dispatches, selectedDispatchId],
  );

  useEffect(() => {
    if (!selected && dispatches.length > 0) {
      setSelectedDispatchId(dispatches[0].dispatch_id);
    }
  }, [dispatches, selected]);

  useEffect(() => {
    let active = true;
    const loadLog = async () => {
      if (!selected) {
        setLogText("");
        return;
      }
      const rel =
        logTab === "dispatch_stdout"
          ? selected.stdout_rel
          : logTab === "dispatch_stderr"
            ? selected.stderr_rel
            : logTab === "verifier_stdout"
              ? selected.verifier_stdout_rel
              : selected.verifier_stderr_rel;
      if (!rel) {
        setLogText("(no file)");
        return;
      }
      try {
        const tick = typeof selected.member_tick_u64 === "number" ? selected.member_tick_u64 : typeof selected.tick_u64 === "number" ? selected.tick_u64 : undefined;
        const text = await fetchTextFile(runId, rel, tick);
        if (active) {
          setLogText(text);
        }
      } catch (err) {
        if (active) {
          setLogText(err instanceof Error ? err.message : "failed to load log");
        }
      }
    };

    void loadLog();
    const timer = setInterval(() => {
      void loadLog();
    }, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [runId, selected, logTab]);

  useEffect(() => {
    let active = true;
    const loadDetails = async () => {
      if (!selected) {
        setPromoBundle(null);
        setDiffs([]);
        setProofs([]);
        return;
      }
      setLoadingDetails(true);
      try {
        setRepoDiffDisabled(false);
        const promo = await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}/dispatch/${encodeURIComponent(selected.dispatch_id)}/promotion-bundle`);
        if (!active) {
          return;
        }
        setPromoBundle(promo.payload ?? null);

        const touched: string[] = Array.isArray(promo?.payload?.touched_paths) ? promo.payload.touched_paths : [];
        const subrunRootRel = selected.subrun_root_rel;

        const diffRows: Array<{ path: string; text: string }> = [];
        for (const relPath of touched) {
          let current = "(missing in repo)";
          let candidate = "(missing in subrun)";
          try {
            const res = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/repo-file?rel=${encodeURIComponent(relPath)}`, { cache: "no-store" });
            if (res.status === 403) {
              if (active) {
                setRepoDiffDisabled(true);
              }
              current = "repo diff disabled (set env flag)";
            } else {
              current = await res.text();
            }
          } catch {
            // keep placeholder
          }
          if (subrunRootRel) {
            try {
              const tick = typeof selected.member_tick_u64 === "number" ? selected.member_tick_u64 : typeof selected.tick_u64 === "number" ? selected.tick_u64 : undefined;
              candidate = await fetchTextFile(runId, `${subrunRootRel}/${relPath}`, tick);
            } catch {
              // keep placeholder
            }
          }
          const patch = createTwoFilesPatch(`current/${relPath}`, `candidate/${relPath}`, current, candidate, "repo", "subrun");
          diffRows.push({ path: relPath, text: patch });
        }

        if (active) {
          setDiffs(diffRows);
        }

        const proofsPayload = await fetchJson(`/api/v1/runs/${encodeURIComponent(runId)}/dispatch/${encodeURIComponent(selected.dispatch_id)}/proofs`);
        if (active) {
          setProofs(Array.isArray(proofsPayload.files) ? proofsPayload.files : []);
          if (Array.isArray(proofsPayload.files) && proofsPayload.files.length > 0) {
            setProofOpenRel(proofsPayload.files[0].rel);
          }
        }
      } catch (err) {
        if (active) {
          setPromoBundle({ error: err instanceof Error ? err.message : "failed" });
        }
      } finally {
        if (active) {
          setLoadingDetails(false);
        }
      }
    };
    void loadDetails();
    return () => {
      active = false;
    };
  }, [runId, selected]);

  const openProof = proofs.find((p) => p.rel === proofOpenRel) ?? null;

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1.2fr" }}>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Active Campaign Stream</h3>
        <p style={{ marginTop: 0, color: "var(--ink-muted)", fontSize: 13 }}>last {Math.min(50, dispatches.length)} dispatches</p>
        <div className="card" style={{ maxHeight: 400, overflow: "auto", padding: 0 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ position: "sticky", top: 0, background: "#f0f4fb" }}>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>tick</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>campaign</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>capability</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>code</th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 12 }}>verifier</th>
              </tr>
            </thead>
            <tbody>
              {dispatches.map((row) => (
                <tr
                  key={row.dispatch_id}
                  onClick={() => setSelectedDispatchId(row.dispatch_id)}
                  style={{ cursor: "pointer", background: row.dispatch_id === selected?.dispatch_id ? "#e4ecff" : "transparent" }}
                >
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.tick_u64}</td>
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.campaign_id}</td>
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.capability_id}</td>
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.return_code}</td>
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{row.subverifier_status ?? "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Log Tail Panel</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {([
              ["dispatch_stdout", "Dispatch stdout"],
              ["dispatch_stderr", "Dispatch stderr"],
              ["verifier_stdout", "Verifier stdout"],
              ["verifier_stderr", "Verifier stderr"],
            ] as const).map(([tab, label]) => (
              <button
                key={tab}
                type="button"
                className="btn"
                style={{ background: logTab === tab ? "#e4ecff" : undefined }}
                onClick={() => setLogTab(tab)}
              >
                {label}
              </button>
            ))}
          </div>
          <pre>{logText || "(empty)"}</pre>
        </div>

        <JsonBlock title="Promotion Bundle" value={promoBundle ?? { note: "No promotion receipt" }} />

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Code Diff Viewer</h3>
          {repoDiffDisabled && <p style={{ color: "var(--warn)" }}>repo diff disabled (set env flag).</p>}
          {loadingDetails && <p>Loading dispatch details...</p>}
          {!loadingDetails && diffs.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No touched paths available.</p>}
          {diffs.map((row) => (
            <details key={row.path} className="card" style={{ marginBottom: 8 }}>
              <summary style={{ cursor: "pointer" }}>{row.path}</summary>
              <pre>{row.text}</pre>
            </details>
          ))}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Proof Explorer</h3>
          {proofs.length === 0 && <p style={{ color: "var(--ink-muted)" }}>No `.lean` files found for this dispatch.</p>}
          {proofs.length > 0 && (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {proofs.map((proof) => (
                  <button
                    key={proof.rel}
                    className="btn"
                    type="button"
                    onClick={() => setProofOpenRel(proof.rel)}
                    style={{ background: proof.rel === proofOpenRel ? "#e4ecff" : undefined }}
                  >
                    {proof.rel}
                  </button>
                ))}
              </div>
              <pre>{openProof?.content ?? "(select a proof file)"}</pre>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
