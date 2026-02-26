"use client";

import { motion } from "framer-motion";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Position,
  type Edge,
  type Node,
} from "reactflow";

const MC_SERVER_BASE =
  process.env.NEXT_PUBLIC_MC_SERVER_BASE ?? "http://127.0.0.1:7890";

type TraceClass =
  | "REASONING"
  | "EXECUTION"
  | "VERIFICATION"
  | "GOVERNANCE"
  | "ERROR"
  | string;

type StreamPayload = {
  ts_unix_ms: number;
  seq?: number;
  trace_class: TraceClass;
  signal: string;
  tick_u64?: number;
  raw_line: string;
  fields?: Record<string, string>;
  [key: string]: unknown;
};

type StateResponse = {
  ts_unix_ms?: number;
  omega_state?: Record<string, unknown>;
  active_bundle?: {
    active_bundle_relpath?: string;
    active_bundle_value?: string;
  };
  host?: {
    rss_bytes?: number;
    vms_bytes?: number;
    cpu_pct?: number;
  };
};

type MissionResponse =
  | {
      ok: true;
      mission_id: string;
      staged_path: string;
    }
  | {
      ok: false;
      error: string;
    };

type GoalBuckets = {
  pending: string[];
  active: string[];
  completed: string[];
};

const FLOW_NODE_STYLE = {
  background: "#0f172a",
  color: "#e2e8f0",
  border: "1px solid rgba(148, 163, 184, 0.35)",
  borderRadius: "12px",
  fontSize: 12,
  padding: 8,
};

const PANEL_VARIANTS = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

function stringifySafe(input: unknown): string {
  if (typeof input === "string") {
    return input;
  }
  try {
    return JSON.stringify(input);
  } catch {
    return String(input);
  }
}

function normalizeFields(input: unknown): Record<string, string> {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const normalized: Record<string, string> = {};
  for (const [key, value] of Object.entries(input)) {
    normalized[key] = stringifySafe(value);
  }
  return normalized;
}

function formatBytes(bytes?: number): string {
  if (typeof bytes !== "number" || Number.isNaN(bytes)) {
    return "n/a";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unitIndex = 0;
  let value = bytes;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function formatTimestamp(unixMs?: number): string {
  if (!unixMs) {
    return "--:--:--";
  }
  return new Date(unixMs).toLocaleTimeString();
}

function eventTone(traceClass: TraceClass): string {
  switch (traceClass) {
    case "REASONING":
      return "border-violet-400/50 bg-violet-500/10";
    case "EXECUTION":
      return "border-emerald-400/50 bg-emerald-500/10";
    case "VERIFICATION":
      return "border-sky-400/50 bg-sky-500/10";
    case "GOVERNANCE":
      return "border-slate-400/50 bg-slate-400/10";
    default:
      return "border-rose-400/60 bg-rose-500/10";
  }
}

function formatGoalLabel(item: unknown): string {
  if (typeof item === "string") {
    return item;
  }
  if (typeof item === "number" || typeof item === "boolean") {
    return String(item);
  }
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>;
    const preferred = [
      record.goal,
      record.objective,
      record.title,
      record.name,
      record.id,
    ].find((value) => typeof value === "string" && value.length > 0);
    return preferred ? String(preferred) : stringifySafe(item);
  }
  return stringifySafe(item);
}

function normalizeGoalList(list: unknown): string[] {
  if (!list) {
    return [];
  }
  if (Array.isArray(list)) {
    return list.map(formatGoalLabel);
  }
  if (typeof list === "object") {
    return Object.entries(list as Record<string, unknown>).map(
      ([key, value]) => `${key}: ${formatGoalLabel(value)}`,
    );
  }
  return [String(list)];
}

function extractGoalBuckets(goalQueue: unknown): GoalBuckets {
  const empty: GoalBuckets = { pending: [], active: [], completed: [] };
  if (!goalQueue) {
    return empty;
  }

  if (Array.isArray(goalQueue)) {
    for (const item of goalQueue) {
      const label = formatGoalLabel(item);
      const status =
        item && typeof item === "object" && "status" in item
          ? String((item as Record<string, unknown>).status ?? "pending")
          : "pending";
      const normalizedStatus = status.toLowerCase();
      if (normalizedStatus.includes("complete") || normalizedStatus === "done") {
        empty.completed.push(label);
      } else if (
        normalizedStatus.includes("active") ||
        normalizedStatus.includes("progress") ||
        normalizedStatus.includes("running")
      ) {
        empty.active.push(label);
      } else {
        empty.pending.push(label);
      }
    }
    return empty;
  }

  if (typeof goalQueue === "object") {
    const queue = goalQueue as Record<string, unknown>;
    if (
      "pending" in queue ||
      "active" in queue ||
      "completed" in queue ||
      "complete" in queue
    ) {
      return {
        pending: normalizeGoalList(queue.pending),
        active: normalizeGoalList(queue.active),
        completed: normalizeGoalList(queue.completed ?? queue.complete),
      };
    }
    if ("items" in queue) {
      return extractGoalBuckets(queue.items);
    }
  }

  return empty;
}

export default function Home() {
  const [missionText, setMissionText] = useState("");
  const [missionFeedback, setMissionFeedback] = useState<string | null>(null);
  const [stateSnapshot, setStateSnapshot] = useState<StateResponse | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [streamEvents, setStreamEvents] = useState<StreamPayload[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [latestArtifact, setLatestArtifact] = useState<StreamPayload | null>(
    null,
  );
  const [goalBuckets, setGoalBuckets] = useState<GoalBuckets>({
    pending: [],
    active: [],
    completed: [],
  });
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  const monologueRef = useRef<HTMLDivElement | null>(null);
  const seenSeqRef = useRef(new Set<number>());
  const nodeIdByKeyRef = useRef(new Map<string, string>());
  const nodeCounterRef = useRef(0);
  const tickNodeRef = useRef(new Map<number, string>());
  const edgeSetRef = useRef(new Set<string>());

  const appendEvent = useCallback((incoming: StreamPayload) => {
    setStreamEvents((previous) => [...previous.slice(-399), incoming]);
    if (
      incoming.signal === "ACTIVATION_COMMIT" ||
      incoming.signal === "CCAP_DECISION"
    ) {
      setLatestArtifact(incoming);
    }

    const capabilityOrDomain =
      incoming.fields?.capability ?? incoming.fields?.domain;
    const nodeKey = capabilityOrDomain
      ? `${incoming.signal}:${capabilityOrDomain}`
      : incoming.signal;

    let nodeId = nodeIdByKeyRef.current.get(nodeKey);
    if (!nodeId) {
      const createdNodeId = `node-${nodeIdByKeyRef.current.size + 1}`;
      nodeIdByKeyRef.current.set(nodeKey, createdNodeId);
      nodeId = createdNodeId;
      const index = nodeCounterRef.current++;
      const x = (index % 3) * 240;
      const y = Math.floor(index / 3) * 140;
      const label = capabilityOrDomain
        ? `${incoming.signal}\n${capabilityOrDomain}`
        : incoming.signal;
      setNodes((previous) => [
        ...previous,
        {
          id: createdNodeId,
          data: { label },
          position: { x, y },
          style: FLOW_NODE_STYLE,
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
        },
      ]);
    }

    if (typeof incoming.tick_u64 === "number") {
      const lastNodeOnTick = tickNodeRef.current.get(incoming.tick_u64);
      if (lastNodeOnTick && lastNodeOnTick !== nodeId) {
        const edgeId = `tick-${incoming.tick_u64}-${lastNodeOnTick}-${nodeId}`;
        if (!edgeSetRef.current.has(edgeId)) {
          edgeSetRef.current.add(edgeId);
          setEdges((previous) => [
            ...previous,
            {
              id: edgeId,
              source: lastNodeOnTick,
              target: nodeId,
              animated: true,
              markerEnd: { type: MarkerType.ArrowClosed },
              style: { stroke: "#38bdf8", strokeWidth: 1.4 },
            },
          ]);
        }
      }
      tickNodeRef.current.set(incoming.tick_u64, nodeId);
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (stopped) {
        return;
      }
      source = new EventSource(`${MC_SERVER_BASE}/stream`);
      source.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data) as Record<string, unknown>;
          if (typeof payload.seq === "number") {
            if (seenSeqRef.current.has(payload.seq)) {
              return;
            }
            seenSeqRef.current.add(payload.seq);
          }

          setStreamError(null);
          appendEvent({
            ...payload,
            ts_unix_ms:
              typeof payload.ts_unix_ms === "number"
                ? payload.ts_unix_ms
                : Date.now(),
            seq: typeof payload.seq === "number" ? payload.seq : undefined,
            trace_class:
              typeof payload.trace_class === "string"
                ? payload.trace_class
                : "GOVERNANCE",
            signal:
              typeof payload.signal === "string"
                ? payload.signal
                : "UNKNOWN_SIGNAL",
            tick_u64:
              typeof payload.tick_u64 === "number" ? payload.tick_u64 : undefined,
            raw_line:
              typeof payload.raw_line === "string"
                ? payload.raw_line
                : message.data,
            fields: normalizeFields(payload.fields),
          });
        } catch {
          appendEvent({
            ts_unix_ms: Date.now(),
            trace_class: "ERROR",
            signal: "STREAM_PARSE_ERROR",
            raw_line: message.data,
            fields: {},
          });
        }
      };
      source.onerror = () => {
        setStreamError("stream disconnected, reconnecting in 1s");
        source?.close();
        reconnectTimer = setTimeout(connect, 1000);
      };
    };

    connect();
    return () => {
      stopped = true;
      source?.close();
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
    };
  }, [appendEvent]);

  useEffect(() => {
    let alive = true;

    const pullState = async () => {
      try {
        const response = await fetch(`${MC_SERVER_BASE}/api/state/current`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`HTTP_${response.status}`);
        }
        const payload = (await response.json()) as StateResponse;
        if (!alive) {
          return;
        }
        setStateSnapshot(payload);
        setGoalBuckets(extractGoalBuckets(payload.omega_state?.goal_queue));
        setStateError(null);
      } catch (error) {
        if (!alive) {
          return;
        }
        setStateError(error instanceof Error ? error.message : "state unavailable");
      }
    };

    pullState();
    const interval = setInterval(pullState, 1000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (monologueRef.current) {
      monologueRef.current.scrollTop = monologueRef.current.scrollHeight;
    }
  }, [streamEvents]);

  const submitMission = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const intent = missionText.trim();
    if (!intent) {
      setMissionFeedback("error: mission objective required");
      return;
    }

    setMissionFeedback("submitting...");
    try {
      const response = await fetch(`${MC_SERVER_BASE}/api/mission`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ human_intent_str: intent }),
      });
      const payload = (await response.json()) as MissionResponse;
      if (payload.ok) {
        setMissionFeedback(
          `mission_id: ${payload.mission_id} | staged_path: ${payload.staged_path}`,
        );
      } else {
        setMissionFeedback(`error: ${payload.error}`);
      }
    } catch (error) {
      setMissionFeedback(
        `error: ${error instanceof Error ? error.message : "request failed"}`,
      );
    }
  };

  const activeBundleValue =
    stateSnapshot?.active_bundle?.active_bundle_value ?? "n/a";
  const cpuPct = stateSnapshot?.host?.cpu_pct;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_15%_15%,#164e63_0%,#0b1024_40%,#040611_100%)] text-slate-100">
      <div className="mx-auto flex w-full max-w-[1800px] flex-col gap-4 p-4 pb-8 lg:p-6">
        <motion.header
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="rounded-2xl border border-white/10 bg-slate-900/70 p-4 backdrop-blur"
        >
          <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
            Mission Control
          </h1>
          <p className="font-mono text-xs text-slate-300">
            base: {MC_SERVER_BASE}
          </p>
        </motion.header>

        <div className="grid gap-4 xl:grid-cols-[1.08fr_1.65fr_1fr]">
          <motion.section
            variants={PANEL_VARIANTS}
            initial="hidden"
            animate="show"
            transition={{ duration: 0.32, delay: 0.05 }}
            className="rounded-2xl border border-white/10 bg-slate-900/70 p-4 backdrop-blur"
          >
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">
              Command Console
            </h2>

            <form className="flex flex-col gap-3" onSubmit={submitMission}>
              <input
                value={missionText}
                onChange={(event) => setMissionText(event.target.value)}
                placeholder="> ENTER MISSION OBJECTIVE..."
                className="w-full rounded-xl border border-cyan-300/25 bg-slate-950/80 px-3 py-2 font-mono text-sm text-cyan-100 outline-none transition focus:border-cyan-300/70"
              />
              <button
                type="submit"
                className="rounded-xl border border-cyan-300/35 bg-cyan-400/15 px-3 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-300/25"
              >
                Submit Mission
              </button>
            </form>

            <p className="mt-3 min-h-10 rounded-xl border border-white/10 bg-slate-950/70 p-2 font-mono text-xs text-slate-200">
              {missionFeedback ?? "mission response pending"}
            </p>

            <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
              Goal Queue
            </h3>
            <div className="mt-2 grid gap-2 md:grid-cols-3 xl:grid-cols-1">
              {([
                ["pending", goalBuckets.pending],
                ["active", goalBuckets.active],
                ["completed", goalBuckets.completed],
              ] as const).map(([label, values]) => (
                <div
                  key={label}
                  className="rounded-xl border border-white/10 bg-slate-950/65 p-2"
                >
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-slate-400">
                    {label}
                  </p>
                  <ul className="space-y-1 text-xs text-slate-200">
                    {(values.length ? values : ["--"]).slice(0, 8).map((goal) => (
                      <li
                        key={`${label}-${goal}`}
                        className="truncate rounded-md border border-white/5 bg-slate-900/70 px-2 py-1"
                        title={goal}
                      >
                        {goal}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
              System Health
            </h3>
            <div className="mt-2 rounded-xl border border-white/10 bg-slate-950/65 p-3 text-sm">
              <p className="flex justify-between gap-3">
                <span className="text-slate-400">RSS</span>
                <span className="font-mono text-cyan-100">
                  {formatBytes(stateSnapshot?.host?.rss_bytes)}
                </span>
              </p>
              <p className="mt-1 flex justify-between gap-3">
                <span className="text-slate-400">CPU</span>
                <span className="font-mono text-cyan-100">
                  {typeof cpuPct === "number" ? `${cpuPct.toFixed(2)}%` : "n/a"}
                </span>
              </p>
              <p className="mt-2 font-mono text-[11px] text-rose-300/90">
                {stateError ?? "state polling @1Hz"}
              </p>
            </div>
          </motion.section>

          <motion.section
            variants={PANEL_VARIANTS}
            initial="hidden"
            animate="show"
            transition={{ duration: 0.32, delay: 0.1 }}
            className="rounded-2xl border border-white/10 bg-slate-900/70 p-4 backdrop-blur"
          >
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">
              Live Monologue
            </h2>
            <div
              ref={monologueRef}
              className="h-72 space-y-2 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/60 p-2 md:h-80"
            >
              {streamEvents.length === 0 ? (
                <p className="px-2 py-3 font-mono text-xs text-slate-400">
                  waiting for SSE events...
                </p>
              ) : (
                streamEvents.map((event, index) => (
                  <motion.div
                    key={`${event.seq ?? "no-seq"}-${event.ts_unix_ms}-${index}`}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18 }}
                    className={`rounded-lg border p-2 ${eventTone(event.trace_class)}`}
                  >
                    <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-300">
                      {formatTimestamp(event.ts_unix_ms)} | {event.trace_class} |{" "}
                      {event.signal}
                    </p>
                    <p className="mt-1 font-mono text-xs text-slate-100">
                      {event.raw_line}
                    </p>
                  </motion.div>
                ))
              )}
            </div>
            <p className="mt-2 font-mono text-[11px] text-rose-300/90">
              {streamError ?? "sse connected"}
            </p>

            <h3 className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
              Signal DAG
            </h3>
            <div className="mt-2 h-80 rounded-xl border border-white/10 bg-slate-950/75">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                fitView
                defaultEdgeOptions={{
                  type: "smoothstep",
                  markerEnd: { type: MarkerType.ArrowClosed },
                }}
                proOptions={{ hideAttribution: true }}
              >
                <MiniMap
                  pannable
                  zoomable
                  style={{ backgroundColor: "#020617", borderRadius: 8 }}
                />
                <Controls showInteractive={false} />
                <Background color="#1e293b" gap={20} size={1} />
              </ReactFlow>
            </div>
          </motion.section>

          <motion.section
            variants={PANEL_VARIANTS}
            initial="hidden"
            animate="show"
            transition={{ duration: 0.32, delay: 0.15 }}
            className="rounded-2xl border border-white/10 bg-slate-900/70 p-4 backdrop-blur"
          >
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">
              Artifact Inspector
            </h2>

            <div className="rounded-xl border border-white/10 bg-slate-950/60 p-3">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
                active_bundle_value
              </p>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-slate-900/70 p-2 font-mono text-xs text-cyan-100">
                {activeBundleValue}
              </pre>
            </div>

            <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/60 p-3">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
                latest important artifact
              </p>
              <pre className="mt-2 h-72 overflow-auto rounded-lg border border-white/10 bg-slate-900/70 p-2 font-mono text-xs text-slate-200 md:h-[26rem]">
                {latestArtifact
                  ? JSON.stringify(latestArtifact, null, 2)
                  : "awaiting ACTIVATION_COMMIT / CCAP_DECISION"}
              </pre>
            </div>

            <p className="mt-3 font-mono text-[11px] text-slate-400">
              snapshot: {formatTimestamp(stateSnapshot?.ts_unix_ms)}
            </p>
          </motion.section>
        </div>
      </div>
    </main>
  );
}
