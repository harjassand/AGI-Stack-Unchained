"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

const MC_SERVER_BASE =
  process.env.NEXT_PUBLIC_MC_SERVER_BASE ?? "http://127.0.0.1:7890";

type StreamPayload = {
  ts_unix_ms: number;
  seq?: number;
  trace_class: string;
  signal: string;
  tick_u64?: number;
  raw_line: string;
  fields?: Record<string, string>;
  event_type?: string;
  mission_id?: string;
  payload?: Record<string, unknown>;
};

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

type StatePayload = {
  omega_state?: Record<string, unknown>;
  mission_control?: {
    summary?: {
      found_b?: boolean;
      mission_id?: string;
      mission_graph_id?: string;
      selected_branch_id?: string;
      evidence_pack_id?: string;
      replay_verify?: {
        ok_b?: boolean;
        reason_code?: string;
      };
      intent_branches?: Array<{
        branch_id?: string;
        title?: string;
        confidence_q32?: number;
      }>;
      state?: {
        status?: string;
        active_node_id?: string | null;
        completed_count_u64?: number;
        total_node_results_u64?: number;
        last_tick_u64?: number;
        completed_node_ids?: string[];
      };
    };
    recent_events?: Array<{
      event_type?: string;
      mission_id?: string;
      tick_u64?: number;
      payload?: Record<string, unknown>;
    }>;
  };
};

type ChatDirectResponse = {
  ok: true;
  kind: "DIRECT_ANSWER";
  assistant_message: string;
  confidence: "HIGH" | "MED" | "LOW";
};

type ChatMissionResponse = {
  ok: true;
  kind: "MISSION";
  assistant_message: string;
  mission_staged_path: string;
  mission_request_preview: Record<string, unknown>;
  mission_id?: string;
  compile_receipt?: {
    ok_b?: boolean;
    reason_code?: string;
    selected_branch_id?: string;
    mission_graph_id?: string;
    required_clarifications?: Array<{
      question?: string;
      path?: string;
      blocking_b?: boolean;
    }>;
  };
  mission_graph_id?: string;
  mission_state?: {
    status?: string;
    active_node_id?: string | null;
    completed_count_u64?: number;
  };
  evidence_pack_id?: string | null;
  replay_verify?: {
    ok_b?: boolean;
    reason_code?: string;
  } | null;
};

type ChatFailureResponse = {
  ok: false;
  error: string;
};

type ChatResponse = ChatDirectResponse | ChatMissionResponse | ChatFailureResponse;

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  mission: boolean;
  missionMeta?: {
    missionId?: string;
    selectedBranchId?: string;
  };
};

function mapFriendlySignal(signal: string): string {
  if (signal === "LOG_NOT_FOUND") {
    return "Daemon log not detected.";
  }
  if (signal === "LOG_SOURCE_SELECTED") {
    return "Daemon log source selected.";
  }
  if (!signal) {
    return "No stream signal yet.";
  }
  const lowered = signal.toLowerCase().replace(/_/g, " ");
  return lowered.charAt(0).toUpperCase() + lowered.slice(1);
}

function extractTick(state: StatePayload | null): string {
  const omegaState = state?.omega_state;
  if (!omegaState || typeof omegaState !== "object") {
    return "n/a";
  }
  const directTick = omegaState.tick_u64 ?? omegaState.tick;
  if (typeof directTick === "number" || typeof directTick === "string") {
    return String(directTick);
  }

  const runtime = omegaState.runtime;
  if (runtime && typeof runtime === "object") {
    const nested = (runtime as Record<string, unknown>).tick_u64;
    if (typeof nested === "number" || typeof nested === "string") {
      return String(nested);
    }
  }

  return "n/a";
}

function StatusPill({
  label,
  state,
}: {
  label: string;
  state: "good" | "warn" | "bad";
}) {
  const tone =
    state === "good"
      ? "border-mc-success/50 bg-mc-success/15 text-mc-success"
      : state === "warn"
        ? "border-amber-400/40 bg-amber-500/10 text-amber-200"
        : "border-mc-danger/45 bg-mc-danger/10 text-mc-danger";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide ${tone}`}
    >
      {label}
    </span>
  );
}

export default function Home() {
  const [inputText, setInputText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [statePayload, setStatePayload] = useState<StatePayload | null>(null);
  const [sseOpen, setSseOpen] = useState(false);
  const [lastSseEventMs, setLastSseEventMs] = useState<number>(0);
  const [nowMs, setNowMs] = useState<number>(Date.now());
  const [streamEvents, setStreamEvents] = useState<StreamPayload[]>([]);
  const [showRawStream, setShowRawStream] = useState(false);

  const idRef = useRef(0);
  const listEndRef = useRef<HTMLDivElement | null>(null);

  const verifiedReceiptsCount = useMemo(
    () => streamEvents.filter((event) => event.trace_class === "VERIFICATION").length,
    [streamEvents],
  );
  const latestSignal = streamEvents.length > 0 ? streamEvents[streamEvents.length - 1].signal : "";
  const currentTick = extractTick(statePayload);
  const daemonDetected = Boolean(health?.log?.found_b && health?.state?.found_b);
  const missionSummary = statePayload?.mission_control?.summary;
  const missionState = missionSummary?.state;
  const missionEvents = useMemo(
    () =>
      (statePayload?.mission_control?.recent_events ?? []).filter((event) =>
        Boolean(event?.event_type?.startsWith("MISSION_NODE_")),
      ),
    [statePayload],
  );

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamEvents.length]);

  useEffect(() => {
    const source = new EventSource(`${MC_SERVER_BASE}/stream`);

    source.onopen = () => {
      setSseOpen(true);
    };

    source.onmessage = (event) => {
      setLastSseEventMs(Date.now());
      try {
        const payload = JSON.parse(event.data) as StreamPayload;
        setStreamEvents((previous) => [...previous.slice(-299), payload]);
      } catch {
        // Ignore malformed SSE event payloads.
      }
    };

    source.onerror = () => {
      setSseOpen(false);
    };

    return () => {
      source.close();
      setSseOpen(false);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const pollHealth = async () => {
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

    void pollHealth();
    const interval = window.setInterval(() => {
      void pollHealth();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const pollState = async () => {
      try {
        const response = await fetch(`${MC_SERVER_BASE}/api/state/current`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`HTTP_${response.status}`);
        }
        const payload = (await response.json()) as StatePayload;
        if (!cancelled) {
          setStatePayload(payload);
        }
      } catch {
        if (!cancelled) {
          setStatePayload(null);
        }
      }
    };

    void pollState();
    const interval = window.setInterval(() => {
      void pollState();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const sseHealthy = sseOpen && nowMs - lastSseEventMs <= 5000;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = inputText.trim();
    if (!message || isSubmitting) {
      return;
    }

    setInputText("");
    setMessages((previous) => [
      ...previous,
      { id: ++idRef.current, role: "user", text: message, mission: false },
    ]);
    setIsSubmitting(true);

    try {
      const response = await fetch(`${MC_SERVER_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({ message, mode: "customer" }),
      });

      const payload = (await response.json()) as ChatResponse;
      if (payload.ok && payload.kind === "DIRECT_ANSWER") {
        setMessages((previous) => [
          ...previous,
          {
            id: ++idRef.current,
            role: "assistant",
            text: payload.assistant_message,
            mission: false,
          },
        ]);
      } else if (payload.ok && payload.kind === "MISSION") {
        const missionId = payload.mission_id;
        const selectedBranchId = payload.compile_receipt?.selected_branch_id;
        const clarificationCount = payload.compile_receipt?.required_clarifications?.length ?? 0;
        const status = payload.mission_state?.status ?? "RUNNING";
        setMessages((previous) => [
          ...previous,
          {
            id: ++idRef.current,
            role: "assistant",
            text:
              clarificationCount > 0
                ? `Clarification required (${clarificationCount}).`
                : `Queued mission ${missionId ?? ""} (${status}).`,
            mission: true,
            missionMeta: {
              missionId,
              selectedBranchId,
            },
          },
        ]);
      } else {
        setMessages((previous) => [
          ...previous,
          {
            id: ++idRef.current,
            role: "assistant",
            text: `Request failed: ${(payload as ChatFailureResponse).error || "unknown_error"}`,
            mission: false,
          },
        ]);
      }
    } catch {
      setMessages((previous) => [
        ...previous,
        {
          id: ++idRef.current,
          role: "assistant",
          text: "Request failed: unable to reach mission control API.",
          mission: false,
        },
      ]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(1200px_circle_at_50%_-20%,hsl(var(--mc-bg-1))_0%,hsl(var(--mc-bg-0))_60%,#000_100%)] text-mc-fg">
      <div className="max-w-3xl mx-auto px-4 pb-32 pt-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-mc-muted2">Control Plane</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Mission Control</h1>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex flex-wrap justify-end gap-2">
              <StatusPill label="API" state={health?.ok ? "good" : "bad"} />
              <StatusPill
                label="SSE"
                state={sseHealthy ? "good" : sseOpen ? "warn" : "warn"}
              />
              <StatusPill label="LOG" state={health?.log?.found_b ? "good" : "bad"} />
              <StatusPill
                label="STATE"
                state={health?.state?.found_b ? "good" : "bad"}
              />
            </div>
            <button
              type="button"
              className="text-xs font-medium text-mc-muted transition-colors hover:text-mc-fg"
              onClick={() => setShowRawStream((value) => !value)}
            >
              {showRawStream ? "Hide raw stream" : "Show raw stream"}
            </button>
          </div>
        </header>

        <section className="mt-5 h-[calc(100vh-210px)] overflow-y-auto rounded-2xl border border-mc-border bg-mc-surface/55 p-4 shadow-[0_20px_80px_rgba(0,0,0,0.35)]">
          {messages.length === 0 ? (
            <div className="rounded-xl border border-dashed border-mc-border/90 bg-mc-surface2/45 px-4 py-6 text-sm text-mc-muted">
              Ask a question. Arithmetic answers return immediately. Non-trivial requests queue a mission.
            </div>
          ) : null}

          <div className="space-y-4">
            {messages.map((message) => {
              const isUser = message.role === "user";
              return (
                <div
                  key={message.id}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div className="max-w-[85%]">
                    <div
                      className={`rounded-2xl border px-4 py-3 text-sm leading-relaxed ${
                        isUser
                          ? "border-mc-accent/30 bg-mc-accent/15 text-mc-fg"
                          : "border-mc-border bg-mc-surface2/80 text-mc-fg"
                      }`}
                    >
                      {message.text}
                    </div>
                    {message.mission ? (
                      <div className="mt-2 rounded-xl border border-mc-border bg-mc-surface/90 p-3 text-xs text-mc-muted">
                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                          <div>
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Tick</p>
                            <p className="mt-1 font-medium text-mc-fg">{currentTick}</p>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Last signal</p>
                            <p className="mt-1 font-medium text-mc-fg">
                              {mapFriendlySignal(latestSignal)}
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Verified receipts</p>
                            <p className="mt-1 font-medium text-mc-fg">{verifiedReceiptsCount}</p>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Mission status</p>
                            <p className="mt-1 font-medium text-mc-fg">{missionState?.status ?? "n/a"}</p>
                          </div>
                        </div>

                        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div className="rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Branch Selection</p>
                            <p className="mt-1 text-mc-fg">
                              {message.missionMeta?.selectedBranchId ??
                                missionSummary?.selected_branch_id ??
                                "n/a"}
                            </p>
                          </div>
                          <div className="rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Mission Graph</p>
                            <p className="mt-1 text-mc-fg">
                              {missionSummary?.mission_graph_id ?? "n/a"}
                            </p>
                          </div>
                        </div>

                        <div className="mt-3 rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-mc-muted2">
                            DAG Progress
                          </p>
                          <p className="mt-1 text-mc-fg">
                            {missionState?.completed_count_u64 ?? 0} completed
                            {" / "}
                            {missionState?.total_node_results_u64 ?? 0} results
                          </p>
                          <p className="text-mc-muted">
                            Active node: {missionState?.active_node_id ?? "none"}
                          </p>
                        </div>

                        {missionSummary?.intent_branches && missionSummary.intent_branches.length > 0 ? (
                          <div className="mt-3 rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                            <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Intent branches</p>
                            <div className="mt-1 space-y-1">
                              {missionSummary.intent_branches.slice(0, 4).map((branch) => (
                                <p key={branch.branch_id} className="text-mc-fg">
                                  {branch.branch_id} · {branch.title} · q32=
                                  {branch.confidence_q32 ?? "n/a"}
                                </p>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <div className="mt-3 rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-mc-muted2">Evidence Pack</p>
                          <p className="mt-1 text-mc-fg">{missionSummary?.evidence_pack_id ?? "pending"}</p>
                          <p className="text-mc-muted">
                            Replay verify:{" "}
                            {missionSummary?.replay_verify?.ok_b === true
                              ? "PASS"
                              : missionSummary?.replay_verify?.ok_b === false
                                ? `FAIL (${missionSummary?.replay_verify?.reason_code ?? "unknown"})`
                                : "pending"}
                          </p>
                        </div>

                        <div className="mt-3 rounded-lg border border-mc-border/80 bg-black/20 px-2 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-mc-muted2">
                            Node Timeline
                          </p>
                          {missionEvents.length === 0 ? (
                            <p className="mt-1 text-mc-muted">No node events yet.</p>
                          ) : (
                            <div className="mt-1 space-y-1">
                              {missionEvents.slice(-6).map((event, idx) => (
                                <p key={`${event.event_type}-${event.tick_u64 ?? 0}-${idx}`} className="text-mc-fg">
                                  t{event.tick_u64 ?? 0} {event.event_type}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                        {!daemonDetected ? (
                          <p className="mt-3 text-mc-danger">
                            Daemon not detected. Start ignite_runaway.sh.
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          {showRawStream ? (
            <div className="mt-4 rounded-xl border border-mc-border bg-black/30 p-3 font-mono text-xs text-mc-muted">
              {streamEvents.length === 0 ? (
                <p>No raw events yet.</p>
              ) : (
                <div className="space-y-1">
                  {streamEvents.slice(-14).map((event) => (
                    <p key={`${event.ts_unix_ms}-${event.seq ?? 0}`}>
                      [{new Date(event.ts_unix_ms).toLocaleTimeString()}] {event.signal}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ) : null}
          <div ref={listEndRef} />
        </section>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-mc-border bg-[hsl(var(--mc-bg-0)/0.76)] backdrop-blur-xl">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <input
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder="Ask Mission Control"
              className="h-11 flex-1 rounded-xl border border-mc-border bg-mc-surface px-4 text-sm text-mc-fg outline-none ring-0 placeholder:text-mc-muted focus:border-mc-accent/60"
            />
            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 rounded-xl border border-mc-accent/50 bg-mc-accent/15 px-4 text-sm font-semibold text-mc-fg transition hover:bg-mc-accent/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Sending" : "Send"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
