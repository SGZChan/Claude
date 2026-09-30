import { useState } from "react";
import { api, ago, pct } from "../api";
import { useApi } from "../hooks";

export function Skills() {
  const [skills, reload] = useApi<any[]>("/api/skills", 4000);
  return (
    <>
      <h1>Skills</h1>
      <p className="sub">Reusable macros Laya learned from repeated successes. The System One router runs them with no model call.</p>
      <div className="card">
        {skills && !skills.length && <div className="empty">Nothing learned yet. A pattern is promoted after it succeeds the same way several times.</div>}
        {!!skills?.length && (
          <table>
            <thead><tr><th>Pattern</th><th>Steps</th><th>Uses</th><th>Success</th><th>Score</th><th>Last used</th><th /></tr></thead>
            <tbody>
              {skills.map((s) => (
                <tr key={s.id} style={{ opacity: s.enabled ? 1 : 0.55 }}>
                  <td><b>{s.shape}</b>{!s.enabled && <span className="badge" style={{ marginLeft: 6 }}>disabled</span>}</td>
                  <td className="mono">{s.steps.map((t: any) => t.tool).join(" → ")}</td>
                  <td>{s.uses}</td>
                  <td>{s.successes + s.failures ? pct(s.successes / (s.successes + s.failures)) : "—"}</td>
                  <td>{s.score.toFixed(2)}</td>
                  <td className="muted">{ago(s.last_used)}</td>
                  <td className="row">
                    <button onClick={() => api.patch(`/api/skills/${s.id}`, { enabled: !s.enabled }).then(reload)}>{s.enabled ? "Disable" : "Enable"}</button>
                    <button className="danger" onClick={() => confirm("Delete this skill?") && api.del(`/api/skills/${s.id}`).then(reload)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

export function Memory() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [text, setText] = useState("");
  const [facts, reload] = useApi<any[]>(`/api/memory?q=${encodeURIComponent(q)}&kind=${kind}`);
  return (
    <>
      <h1>Memory</h1>
      <p className="sub">Notes, lessons and corrections Laya can recall. Search is semantic-ish (hashed embeddings).</p>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input className="grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search memory" aria-label="Search memory" />
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
            <option value="">All kinds</option>{["note", "lesson", "correction"].map((k) => <option key={k}>{k}</option>)}
          </select>
        </div>
        <form className="row" style={{ marginBottom: 12 }} onSubmit={(e) => { e.preventDefault(); if (text.trim()) api.post("/api/memory", { text }).then(() => { setText(""); reload(); }); }}>
          <input className="grow" value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note for Laya to remember" aria-label="New note" />
          <button>Add</button>
        </form>
        {facts && !facts.length && <div className="empty">Nothing here.</div>}
        {!!facts?.length && (
          <table>
            <thead><tr><th>Kind</th><th>Text</th><th>Weight</th><th>Added</th><th /></tr></thead>
            <tbody>
              {facts.map((f) => (
                <tr key={f.id}>
                  <td><span className="badge">{f.kind}</span></td><td>{f.text}</td><td>{(+f.score).toFixed(1)}</td>
                  <td className="muted">{ago(f.created)}</td>
                  <td><button className="danger" onClick={() => api.del(`/api/memory/${f.id}`).then(reload)} aria-label="Delete">✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

export function Learning() {
  const [d, reload] = useApi<any>("/api/learning", 5000);
  const [busy, setBusy] = useState(false);
  if (!d) return <p className="muted">Loading…</p>;
  const lp = d.last_practice;
  return (
    <>
      <h1>Learning</h1>
      <p className="sub">Laya improves by remembering, reflecting, and promoting proven patterns to skills. No model weights change.</p>
      <div className="grid g2">
        <div className="card">
          <h2>Self-practice</h2>
          <p className="muted">Runs verifiable arithmetic tasks so patterns reach the promotion threshold ({d.promote_after} successes).</p>
          <button className="primary" disabled={busy} onClick={() => { setBusy(true); api.post("/api/learning/practice", { n: 9 }).then(reload).finally(() => setBusy(false)); }}>
            {busy ? "Practising…" : "Practise 9 tasks"}
          </button>
          {lp && <p>Last session: {lp.passed}/{lp.tasks} correct · {lp.via_skill} via skills · {lp.new_skills} new skills</p>}
          <p><a href="/api/learning/export.jsonl">Download training data (JSONL)</a></p>
        </div>
        <div className="card">
          <h2>Closest to becoming skills</h2>
          {!d.candidates.length && <div className="empty">No candidates yet.</div>}
          {d.candidates.map((c: any) => (
            <div key={c.shape} className="row"><span className="grow">{c.shape}</span><span className="badge">{c.count}/{d.promote_after}</span></div>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>Recent lessons &amp; corrections</h2>
        {![...d.lessons, ...d.corrections].length && <div className="empty">None yet.</div>}
        <table><tbody>{[...d.corrections, ...d.lessons].slice(0, 30).map((f: any) => <tr key={f.id}><td><span className="badge">{f.kind}</span></td><td>{f.text}</td></tr>)}</tbody></table>
      </div>
    </>
  );
}
