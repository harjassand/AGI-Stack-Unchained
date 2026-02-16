import type { RunInfo, SnapshotPayload } from "@/lib/types_v18";

async function expectJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP_${res.status}`);
  }
  return (await res.json()) as T;
}

export async function fetchRuns(includeTicks = false): Promise<{ runs: RunInfo[] }> {
  const qp = includeTicks ? "?include_ticks=1" : "";
  const res = await fetch(`/api/v1/runs${qp}`, { cache: "no-store" });
  return expectJson(res);
}

export async function fetchSnapshot(runId: string, tick?: number): Promise<{ run_id: string; payload: SnapshotPayload }> {
  const qp = typeof tick === "number" ? `?tick=${tick}` : "";
  const res = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/snapshot${qp}`, { cache: "no-store" });
  return expectJson(res);
}

export async function fetchTextFile(runId: string, rel: string, tick?: number): Promise<string> {
  const qp = new URLSearchParams();
  qp.set("rel", rel);
  if (typeof tick === "number" && Number.isFinite(tick)) {
    qp.set("tick", String(Math.floor(tick)));
  }
  const url = `/api/v1/runs/${encodeURIComponent(runId)}/file?${qp.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return await res.text();
}

export async function fetchTickIndex(runId: string): Promise<{ run_id: string; rows: Array<Record<string, unknown>> }> {
  const res = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/tick-index`, { cache: "no-store" });
  return expectJson(res);
}

export async function fetchHashSearch(runId: string, hash: string): Promise<Record<string, unknown>> {
  const url = `/api/v1/runs/${encodeURIComponent(runId)}/hash-search?hash=${encodeURIComponent(hash)}`;
  const res = await fetch(url, { cache: "no-store" });
  return expectJson(res);
}

export async function fetchTickCompare(runId: string, a: number, b: number): Promise<Record<string, unknown>> {
  const url = `/api/v1/runs/${encodeURIComponent(runId)}/compare-ticks?a=${a}&b=${b}`;
  const res = await fetch(url, { cache: "no-store" });
  return expectJson(res);
}

export async function submitDirective(directive: string): Promise<Record<string, unknown>> {
  const res = await fetch("/api/v1/directives", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ directive }),
  });
  return expectJson(res);
}

export async function uploadDataset(files: FileList): Promise<Record<string, unknown>> {
  const toBase64 = async (file: File): Promise<string> => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  };

  const rows = await Promise.all(
    Array.from(files).map(async (file) => ({
      name: file.name,
      data_base64: await toBase64(file),
    })),
  );
  const res = await fetch("/api/v1/uploads", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ files: rows }),
  });
  return expectJson(res);
}
