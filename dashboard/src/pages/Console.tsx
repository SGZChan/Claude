import { useEffect, useRef, useState } from "react";
import { api, LayaEvent, streamRun } from "../api";
import { Timeline } from "./Runs";

export default function Console({ killed, initialGoal = "" }: { killed: boolean; initialGoal?: string }) {
  const [goal, setGoal] = useState(initialGoal);
  const [rid, setRid] = useState<number | null>(null);
  const [events, setEvents] = useState<LayaEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pending, setPending] = useState<{ tool: string; args: any } | null>(null);
  const off = useRef<() => void>();
  useEffect(() => () => off.current?.(), []);

  const start = async () => {
    if (!goal.trim() || busy) return;
    setErr(""); setEvents([]); setBusy(true); setPending(null);
    try {
      const { id } = await api.post("/api/runs", { goal });
      setRid(id);
      off.current = streamRun(id, (e) => {
        setEvents((p) => [...p, e]);
        if (e.type === "approval_request") setPending({ tool: e.tool, args: e.args });
        if (e.type === "approval_denied" || e.type === "tool_result") setPending(null);
      }, () => { setBusy(false); setPending(null); });
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };
  const answer = events.find((e) => e.type === "final");
  return (
    <>
      <h1>Run console</h1>
      <p className="sub">Give Laya a goal. Watch each step live; approve risky actions.</p>
      <div className="card">
        <form className="row" onSubmit={(e) => { e.preventDefault(); start(); }}>
          <input className="grow" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder='e.g. What is 17*23 and save it to notes' aria-label="Goal" />
          <button className="primary" disabled={busy || killed || !goal.trim()}>Run</button>
          {busy && rid && <button type="button" className="danger" onClick={() => api.post(`/api/runs/${rid}/stop`)}>Stop</button>}
        </form>
        {err && <p className="err">{err}</p>}
        {pending && (
          <div className="card" style={{ marginTop: 12, borderColor: "var(--warn)" }} role="alertdialog" aria-label="Approval needed">
            <b>Approval needed:</b> <span className="mono">{pending.tool}({JSON.stringify(pending.args)})</span>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="primary" onClick={() => api.post(`/api/runs/${rid}/approve`, { approve: true })}>Approve</button>
              <button onClick={() => api.post(`/api/runs/${rid}/approve`, { approve: false })}>Deny</button>
            </div>
          </div>
        )}
        <Timeline events={events} />
        {answer && rid && (
          <div style={{ marginTop: 12 }}>
            <h2>Answer</h2><div>{answer.answer || <span className="muted">(empty)</span>}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => api.post(`/api/runs/${rid}/feedback`, { rating: 1 })} aria-label="Good answer">👍</button>
              <button onClick={() => api.post(`/api/runs/${rid}/feedback`, { rating: -1 })} aria-label="Bad answer">👎</button>
              <a href={`#/runs/${rid}`}>Open trace</a>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
