import { useState } from "react";
import FilePicker, { Source, SourceChips, postEach } from "../FilePicker";

const SUM = ["lines", "valid", "duplicates", "votes", "lessons"] as const;

export default function ImportTraining() {
  const [files, setFiles] = useState<Source[]>([]);
  const [pasted, setPasted] = useState("");
  const [learn, setLearn] = useState(true);
  const [lessons, setLessons] = useState(true);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const sources: Source[] = [...files, ...(pasted.trim() ? [{ name: "pasted text", text: pasted, lines: pasted.split("\n").filter((l) => l.trim()).length }] : [])];
  const total = sources.reduce((n, s) => n + s.lines, 0);

  const go = async (dry: boolean) => {
    setBusy(true); setRes(null);
    const results = await postEach("/api/learning/import", sources, { learn_skills: learn, add_lessons: lessons, dry_run: dry }, "jsonl");
    const agg: any = { dry_run: dry, lines: 0, valid: 0, duplicates: 0, votes: 0, lessons: 0, skills_promoted: [], skipped: [], invalid: [], failed: [] };
    for (const r of results) {
      if (r.error) { agg.failed.push(`${r.name}: ${r.error.includes("feature is off") ? "the “Import training data” feature is off (turn it on in Features)" : r.error}`); continue; }
      SUM.forEach((k) => (agg[k] += r.res[k]));
      agg.skills_promoted.push(...r.res.skills_promoted);
      agg.skipped.push(...r.res.skipped.map((x: any) => ({ ...x, file: r.name })));
      agg.invalid.push(...r.res.invalid.map((x: any) => ({ ...x, file: r.name })));
    }
    agg.files = results.length;
    setRes(agg); setBusy(false);
  };
  const clear = () => { setFiles([]); setPasted(""); setRes(null); };
  const where = (x: any) => (agg_multi(res) ? `${x.file}, ` : "") + `line ${x.line}`;

  return (
    <div className="card">
      <h2>Import training data <span className="muted">— JSONL from “Download training data”</span></h2>
      <p className="muted" style={{ marginTop: 0 }}>Each line is a successful example. Laya counts it as a vote toward a new skill (same rules as real runs) and can store a short lesson. Nothing is executed. Only import files you trust.</p>
      <FilePicker onLoaded={(s) => { setFiles((f) => [...f, ...s]); setRes(null); }} label="Drop one or more .jsonl files here, or click to choose" />
      <SourceChips sources={files} onRemove={(i) => { setFiles((f) => f.filter((_, j) => j !== i)); setRes(null); }} />
      <textarea rows={3} style={{ width: "100%", margin: "10px 0" }} value={pasted} onChange={(e) => { setPasted(e.target.value); setRes(null); }}
        placeholder={'…or paste lines here (a JSON array works too):\n{"prompt": "What is 2*3?", "actions": [{"tool": "calculator", "args": {"expression": "2*3"}, "result": "6"}], "final": "6"}'} aria-label="JSONL text" />
      <div className="row">
        <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={learn} onChange={(e) => setLearn(e.target.checked)} /> Learn skills</label>
        <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={lessons} onChange={(e) => setLessons(e.target.checked)} /> Add lessons to memory</label>
        <span className="grow" />
        {!!sources.length && <span className="muted">{sources.length} source{sources.length === 1 ? "" : "s"} · {total} lines</span>}
        <button onClick={() => go(true)} disabled={busy || !sources.length}>Check</button>
        <button className="primary" onClick={() => go(false)} disabled={busy || !sources.length || (!learn && !lessons)}>{busy ? "Working…" : `Import${files.length > 1 ? ` ${files.length} files` : ""}`}</button>
        {!!sources.length && <button onClick={clear}>Clear</button>}
      </div>
      {res?.failed.map((f: string) => <p key={f} className="err" role="alert">{f}</p>)}
      {res && res.lines + res.failed.length > 0 && (
        <div role="status" style={{ marginTop: 12 }}>
          <b>{res.dry_run ? "Check complete (nothing imported)" : "Import complete"}</b>{res.files > 1 && <span className="muted"> · {res.files} files</span>}
          <div className="grid g4" style={{ margin: "8px 0" }}>
            <div className="kpi"><div className="kpi-label">Lines</div><div className="kpi-value">{res.lines}</div></div>
            <div className="kpi"><div className="kpi-label">Valid</div><div className="kpi-value">{res.valid}</div></div>
            <div className="kpi"><div className="kpi-label">Already imported</div><div className="kpi-value">{res.duplicates}</div></div>
            {!res.dry_run && <div className="kpi"><div className="kpi-label">Skill votes</div><div className="kpi-value">{res.votes}</div></div>}
            {!res.dry_run && <div className="kpi"><div className="kpi-label">Lessons</div><div className="kpi-value">{res.lessons}</div></div>}
          </div>
          {res.skills_promoted.length > 0 && <p>🎉 New skill{res.skills_promoted.length > 1 ? "s" : ""} learned: {res.skills_promoted.map((s: string) => <span key={s} className="badge" style={{ marginRight: 4 }}>{s}</span>)} <a href="#/skills">See Skills</a></p>}
          {res.skipped.length > 0 && <details className="tableview" open><summary>{res.skipped.length} skipped</summary>{res.skipped.map((s: any, i: number) => <div key={i}>{where(s)}: {s.reason}</div>)}</details>}
          {res.invalid.length > 0 && <details className="tableview" open><summary className="err">{res.invalid.length} invalid</summary>{res.invalid.map((s: any, i: number) => <div key={i}>{where(s)}: {s.error}</div>)}</details>}
        </div>
      )}
    </div>
  );
}

const agg_multi = (r: any) => !!r && r.files > 1;
