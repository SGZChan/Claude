import { useState } from "react";
import { api, ago, pct } from "../api";
import { useApi } from "../hooks";
import PracticeTasks from "./Practice";
import ImportTraining from "./ImportTraining";
import FilePicker, { Source, SourceChips, postEach } from "../FilePicker";

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
  const [many, setMany] = useState(false);
  const [files, setFiles] = useState<Source[]>([]);
  const [pasted, setPasted] = useState("");
  const [batchKind, setBatchKind] = useState("note");
  const [batchMsg, setBatchMsg] = useState("");
  const addMany = async () => {
    const sources: Source[] = [...files, ...(pasted.trim() ? [{ name: "pasted text", text: pasted, lines: 0 }] : [])];
    const results = await postEach("/api/memory/batch", sources, { kind: batchKind }, "text");
    const ok = results.filter((r) => r.res), bad = results.filter((r) => r.error);
    const added = ok.reduce((n, r) => n + r.res.added, 0), dups = ok.reduce((n, r) => n + r.res.duplicates, 0);
    const errs = ok.flatMap((r) => r.res.errors.map((e: any) => `${r.name} line ${e.line}: ${e.error}`)).concat(bad.map((r) => `${r.name}: ${r.error}`));
    setBatchMsg(`Added ${added}${dups ? `, ${dups} already there` : ""}${errs.length ? `. Problems: ${errs.slice(0, 5).join("; ")}` : ""}`);
    if (added) { setPasted(""); setFiles([]); reload(); }
  };
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
          <button type="button" onClick={() => setMany(!many)} aria-expanded={many}>Add many…</button>
        </form>
        {many && (
          <div className="card" style={{ background: "var(--surface-2)" }}>
            <p className="hint" style={{ marginTop: 0 }}>One item per line (lines starting with # are ignored, duplicates are skipped). You can also drop several text files.</p>
            <FilePicker onLoaded={(s) => setFiles((f) => [...f, ...s])} label="Drop .txt files here, or click to choose" />
            <SourceChips sources={files} onRemove={(i) => setFiles((f) => f.filter((_, j) => j !== i))} />
            <textarea rows={5} style={{ width: "100%", margin: "10px 0" }} value={pasted} onChange={(e) => setPasted(e.target.value)} aria-label="Many notes" placeholder={"Wifi password is on the fridge\nDentist on Tuesday at 3\nMum's birthday is 12 May"} />
            <div className="row">
              <select value={batchKind} onChange={(e) => setBatchKind(e.target.value)} aria-label="Kind for batch">{["note", "lesson", "correction"].map((k) => <option key={k}>{k}</option>)}</select>
              <button className="primary" type="button" onClick={addMany} disabled={!files.length && !pasted.trim()}>Add all</button>
              {batchMsg && <span role="status">{batchMsg}</span>}
            </div>
          </div>
        )}
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
          <p className="muted">Runs built-in arithmetic plus your own practice tasks (below) so patterns reach the promotion threshold ({d.promote_after} successes).</p>
          <button className="primary" disabled={busy} onClick={() => { setBusy(true); api.post("/api/learning/practice", { n: 9 }).then(reload).finally(() => setBusy(false)); }}>
            {busy ? "Practising…" : "Practise 9 tasks"}
          </button>
          {lp && <p>Last session: {lp.passed}/{lp.tasks} correct · {lp.via_skill} via skills · {lp.new_skills} new skills</p>}
          {lp?.by_task && Object.entries(lp.by_task).map(([n, s]: [string, any]) => <div key={n} className="muted" style={{ fontSize: 12 }}>{n}: {s.passed}/{s.runs}</div>)}
          {lp?.failures?.length > 0 && <details className="tableview"><summary>{lp.failures.length} miss(es)</summary>{lp.failures.map((f: any, i: number) => <div key={i} className="mono">{f.detail}</div>)}</details>}
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
      <PracticeTasks />
      <ImportTraining />
      <div className="card">
        <h2>Recent lessons &amp; corrections</h2>
        {![...d.lessons, ...d.corrections].length && <div className="empty">None yet.</div>}
        <table><tbody>{[...d.corrections, ...d.lessons].slice(0, 30).map((f: any) => <tr key={f.id}><td><span className="badge">{f.kind}</span></td><td>{f.text}</td></tr>)}</tbody></table>
      </div>
    </>
  );
}
