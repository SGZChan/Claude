export type Json = any;

async function req(method: string, url: string, body?: unknown): Promise<Json> {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status} ${r.statusText}`);
  return r.status === 204 ? null : r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}

export const api = {
  get: (u: string) => req("GET", u),
  post: (u: string, b?: unknown) => req("POST", u, b ?? {}),
  patch: (u: string, b: unknown) => req("PATCH", u, b),
  del: (u: string) => req("DELETE", u),
};

export interface LayaEvent {
  type: string; t: number; [k: string]: any;
}

/** Subscribe to a run's event stream (SSE). Returns an unsubscribe function. */
export function streamRun(id: number, onEvent: (e: LayaEvent) => void, onDone: () => void): () => void {
  const es = new EventSource(`/api/runs/${id}/stream`);
  es.onmessage = (m) => onEvent(JSON.parse(m.data));
  es.addEventListener("done", () => { es.close(); onDone(); });
  es.onerror = () => { es.close(); onDone(); };
  return () => es.close();
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const ago = (ts?: number) => {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`;
};
