import { useState } from "react";
import { api, ago, LayaEvent } from "../api";
import { useApi } from "../hooks";

export const Status = ({ s }: { s: string }) => (
  <span className={`badge ${s}`}>{{ ok: "✓", failed: "✕", running: "…", blocked: "⛔", stopped: "■" }[s] ?? "•"} {s}</span>
);

export function Timeline({ events }: { events: LayaEvent[] }) {
  if (!events.length) return null;
  return (
    <div className="timeline">
      {events.map((e, i) => (
        <div key={i} className={`ev ${e.type} ${e.type === "tool_result" && !e.ok ? "bad" : ""}`}>
          <small>{e.t}s · {e.type}</small>{" "}
          {e.type === "route" && (e.via === "skill" ? <>⚡ System One: skill “{e.skill}”</> : <>🧠 Reasoning with the model{e.reason ? ` (${e.reason})` : ""}</>)}
          {e.type === "tool_call" && <span className="mono">{e.tool}({JSON.stringify(e.args)})</span>}
          {e.type === "tool_result" && <span className="mono">{e.ok ? "→" : "✕"} {e.result}</span>}
          {e.type === "approval_request" && <>Approval requested for <span className="mono">{e.tool}</span></>}
          {e.type === "approval_denied" && <>Denied</>}
          {e.type === "final" && <>Answer: {e.answer}</>}
          {e.type === "error" && <>✕ {e.error || e.status}</>}
          {e.type === "invalid_output" && <span className="mono">invalid model output: {e.raw}</span>}
        </div>
      ))}
    </div>
  );
}

export function Runs() {
  const [q, setQ] = useState("");
  const [runs, , err] = useApi<any[]>(`/api/runs?q=${encodeURIComponent(q)}`, 4000);
  return (
    <>
      <h1>Runs</h1>
      <p className="sub">Every goal Laya has handled.</p>
      <div className="card">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search goals and answers" aria-label="Search runs" style={{ width: "100%", marginBottom: 12 }} />
        {err && <p className="err">{err}</p>}
        {runs && !runs.length && <div className="empty">No runs yet.</div>}
        {!!runs?.length && (
          <table>
            <thead><tr><th>Goal</th><th>Status</th><th>Path</th><th>Answer</th><th>Latency</th><th>When</th><th /></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td><a href={`#/runs/${r.id}`}>{r.goal}</a></td>
                  <td><Status s={r.status} /></td>
                  <td>{r.via === "skill" ? "⚡ skill" : r.via}</td>
                  <td>{r.answer}</td>
                  <td>{r.latency ?? "…"}s</td>
                  <td className="muted">{ago(r.started)}</td>
                  <td>{r.feedback > 0 ? "👍" : r.feedback < 0 ? "👎" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

export function RunDetail({ id }: { id: number }) {
  const [r, reload, err] = useApi<any>(`/api/runs/${id}`, 2000);
  const [corr, setCorr] = useState("");
  if (err) return <p className="err">{err}</p>;
  if (!r) return <p className="muted">Loading…</p>;
  const rate = (rating: number) => api.post(`/api/runs/${id}/feedback`, { rating, correction: corr }).then(reload);
  return (
    <>
      <p><a href="#/runs">← All runs</a></p>
      <h1>{r.goal}</h1>
      <p className="sub"><Status s={r.status} /> · {r.via === "skill" ? "⚡ answered by a learned skill" : "reasoned by the model"} · {r.latency ?? "…"}s</p>
      <div className="card">
        <h2>Answer</h2><div>{r.answer || <span className="muted">{r.error || "(none)"}</span>}</div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={() => rate(1)} aria-pressed={r.feedback > 0}>👍</button>
          <button onClick={() => rate(-1)} aria-pressed={r.feedback < 0}>👎</button>
          <input className="grow" value={corr} onChange={(e) => setCorr(e.target.value)} placeholder="Optional correction Laya should remember" aria-label="Correction" />
        </div>
      </div>
      <div className="card"><h2>Trace</h2><Timeline events={r.events} /></div>
    </>
  );
}
