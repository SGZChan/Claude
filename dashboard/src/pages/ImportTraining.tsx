import { useRef, useState } from "react";
import { api } from "../api";

export default function ImportTraining() {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [learn, setLearn] = useState(true);
  const [lessons, setLessons] = useState(true);
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const lines = text.split("\n").filter((l) => l.trim()).length;

  const pick = async (f?: File) => {
    if (!f) return;
    setError(""); setRes(null);
    if (f.size > 5_000_000) { setError("That file is over 5 MB. Split it into smaller files."); return; }
    setText(await f.text()); setFileName(f.name);
  };
  const go = async (dry: boolean) => {
    setBusy(true); setError("");
    try { setRes(await api.post("/api/learning/import", { jsonl: text, learn_skills: learn, add_lessons: lessons, dry_run: dry })); }
    catch (e: any) { setError(e.message); setRes(null); if (String(e.message).includes("feature is off")) setError("The “Import training data” feature is off. Turn it on in Features."); }
    finally { setBusy(false); }
  };
  const clear = () => { setText(""); setFileName(""); setRes(null); setError(""); if (input.current) input.current.value = ""; };

  return (
    <div className="card">
      <h2>Import training data <span className="muted">— JSONL from “Download training data”</span></h2>
      <p className="muted" style={{ marginTop: 0 }}>Each line is a successful example. Laya counts it as a vote toward a new skill (same rules as real runs) and can store a short lesson. Nothing is executed. Only import files you trust.</p>
      <div className="row">
        <input ref={input} type="file" accept=".jsonl,.json,.txt,application/json" aria-label="Choose JSONL file" onChange={(e) => pick(e.target.files?.[0])} />
        {fileName && <span className="muted">{fileName} · {lines} line{lines === 1 ? "" : "s"}</span>}
      </div>
      <textarea rows={4} style={{ width: "100%", margin: "10px 0" }} value={text} onChange={(e) => { setText(e.target.value); setRes(null); }}
        placeholder={'…or paste lines here:\n{"prompt": "What is 2*3?", "actions": [{"tool": "calculator", "args": {"expression": "2*3"}, "result": "6"}], "final": "6"}'} aria-label="JSONL text" />
      <div className="row">
        <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} /> Learn skills</label>
        <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={lessons} onChange={(e) => setLessons(e.target.checked)} /> Add lessons to memory</label>
        <span className="grow" />
        <button onClick={() => go(true)} disabled={busy || !text.trim()}>Check file</button>
        <button className="primary" onClick={() => go(false)} disabled={busy || !text.trim() || (!learn && !lessons)}>{busy ? "Working…" : "Import"}</button>
        {text && <button onClick={clear}>Clear</button>}
      </div>
      {error && <p className="err" role="alert">{error}</p>}
      {res && (
        <div role="status" style={{ marginTop: 12 }}>
          <b>{res.dry_run ? "Check complete (nothing imported)" : "Import complete"}</b>
          <div className="grid g4" style={{ margin: "8px 0" }}>
            <div className="kpi"><div className="kpi-label">Lines</div><div className="kpi-value">{res.lines}</div></div>
            <div className="kpi"><div className="kpi-label">Valid</div><div className="kpi-value">{res.valid}</div></div>
            <div className="kpi"><div className="kpi-label">Already imported</div><div className="kpi-value">{res.duplicates}</div></div>
            {!res.dry_run && <div className="kpi"><div className="kpi-label">Skill votes</div><div className="kpi-value">{res.votes}</div></div>}
            {!res.dry_run && <div className="kpi"><div className="kpi-label">Lessons</div><div className="kpi-value">{res.lessons}</div></div>}
          </div>
          {res.skills_promoted.length > 0 && <p>🎉 New skill{res.skills_promoted.length > 1 ? "s" : ""} learned: {res.skills_promoted.map((s: string) => <span key={s} className="badge" style={{ marginRight: 4 }}>{s}</span>)} <a href="#/skills">See Skills</a></p>}
          {res.skipped.length > 0 && <details className="tableview" open><summary>{res.skipped.length} skipped</summary>{res.skipped.map((s: any) => <div key={s.line}>Line {s.line}: {s.reason}</div>)}</details>}
          {res.invalid.length > 0 && <details className="tableview" open><summary className="err">{res.invalid.length} invalid</summary>{res.invalid.map((s: any) => <div key={s.line}>Line {s.line}: {s.error}</div>)}</details>}
        </div>
      )}
    </div>
  );
}
