"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const MC_SERVER_BASE =
  process.env.NEXT_PUBLIC_MC_SERVER_BASE ?? "http://127.0.0.1:7890";

type HealthPayload = {
  ok: boolean;
  log: {
    found_b: boolean;
    selected_path: string;
    source: string;
  };
  state: {
    found_b: boolean;
    selected_path: string;
    source: string;
  };
  sse: {
    synthetic_log_not_found_emitting_b: boolean;
  };
};

export default function DevClient() {
  const [health, setHealth] = useState<HealthPayload | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const response = await fetch(`${MC_SERVER_BASE}/api/health`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`HTTP_${response.status}`);
        }
        const payload = (await response.json()) as HealthPayload;
        if (!cancelled) {
          setHealth(payload);
        }
      } catch {
        if (!cancelled) {
          setHealth(null);
        }
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <main className="min-h-screen bg-[radial-gradient(1200px_circle_at_50%_-20%,hsl(var(--mc-bg-1))_0%,hsl(var(--mc-bg-0))_60%,#000_100%)] px-4 py-8 text-mc-fg">
      <div className="mx-auto max-w-4xl space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Mission Control Dev UI</h1>
          <Link
            href="/"
            className="rounded-lg border border-mc-border bg-mc-surface px-3 py-2 text-sm text-mc-fg hover:bg-mc-surface2"
          >
            Customer UI
          </Link>
        </div>

        <section className="rounded-xl border border-mc-border bg-mc-surface/80 p-4">
          <p className="text-xs uppercase tracking-wide text-mc-muted2">Selected log path</p>
          <p className="mt-2 break-all font-mono text-sm text-mc-fg">
            {health?.log?.selected_path || "(not found)"}
          </p>
          <p className="mt-1 text-xs text-mc-muted">source={health?.log?.source || "none"}</p>
        </section>

        <section className="rounded-xl border border-mc-border bg-mc-surface/80 p-4">
          <p className="text-xs uppercase tracking-wide text-mc-muted2">Selected state path</p>
          <p className="mt-2 break-all font-mono text-sm text-mc-fg">
            {health?.state?.selected_path || "(not found)"}
          </p>
          <p className="mt-1 text-xs text-mc-muted">source={health?.state?.source || "none"}</p>
        </section>
      </div>
    </main>
  );
}
