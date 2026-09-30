import { useState } from "react";
import { api, pct } from "../api";
import { useApi } from "../hooks";

const CHECKS: Record<string, { label: string; help: string; placeholder: string }> = {
  succeeds: { label: "Just finishes without error", help: "Passes if Laya completes the goal.", placeholder: "" },
  expr: { label: "Number equals expression", help: "Numeric check. Use parameters, e.g. {a}*1.609344. Any number in the answer may match within the tolerance.", placeholder: "{a}*1.609344" },
  contains: { label: "Answer contains text", help: "Case-insensitive.", placeholder: "3 words" },
  equals: { label: "Answer equals text", help: "Whole answer, case-insensitive.", placeholder: "done" },
  regex: { label: "Answer matches regex", help: "Case-insensitive regular expression.", placeholder: "id-\\d+" },
  tool: { label: "A specific tool ran OK", help: "Passes if that tool ran successfully during the run.", placeholder: "date_diff" },
};
const EMPTY = { name: "", template: "", params: "", check_type: "expr", check_value: "", tolerance: 0.001 };

export default function PracticeTasks() {
  const [tasks, reload, err] = useApi<any[]>("/api/practice/tasks", 6000);
  const [form, setForm] = useState<any>(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | "starter" | "">("");
  const [importText, setImportText] = useState("");
  const [showImport, setShowImport] = useState(false);
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  if (err?.includes("feature")) return <div className="card"><h2>Practice tasks</h2><p className="muted">The “Custom practice tasks” feature is off. <a href="#/features">Turn it on in Features</a>.</p></div>;

  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setMsg("");
    try {
      const body = { ...form, tolerance: +form.tolerance };
      if (editing) await api.put(`/api/practice/tasks/${editing}`, body); else await api.post("/api/practice/tasks", body);
      setMsg(editing ? "Task updated (stats reset)." : "Task added."); setForm(EMPTY); setEditing(null); reload();
    } catch (e: any) { setError(e.message); }
  };
  const run = async (t: any, n: number) => {
    setBusy(t.id); setMsg(""); setError("");
    try {
      const r = await api.post(`/api/practice/tasks/${t.id}/run`, { n });
      setMsg(`“${t.name}”: ${r.passed}/${r.tasks} correct${r.new_skills ? ` · ${r.new_skills} new skill(s) learned` : ""}${r.failures.length ? ` · e.g. ${r.failures[0].detail}` : ""}`);
      reload();
    } catch (e: any) { setError(e.message); } finally { setBusy(""); }
  };
  const starter = async () => { setBusy("starter"); const r = await api.post("/api/practice/starter"); setMsg(r.added ? `Added ${r.added} starter task(s).` : "Starter tasks are already added."); setBusy(""); reload(); };
  const doImport = async () => {
    setError("");
    try {
      const parsed = JSON.parse(importText);
      const r = await api.post("/api/practice/import", { tasks: Array.isArray(parsed) ? parsed : parsed.tasks });
      setMsg(`Imported ${r.added} task(s).${r.errors.length ? " Skipped: " + r.errors.join("; ") : ""}`); setImportText(""); setShowImport(false); reload();
    } catch (e: any) { setError(e.message); }
  };
  const edit = (t: any) => { setEditing(t.id); setForm({ name: t.name, template: t.template, params: t.params, check_type: t.check_type, check_value: t.check_value, tolerance: t.tolerance }); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const c = CHECKS[form.check_type];

  return (
    <div className="card">
      <h2>Practice tasks <span className="muted">— your own tasks for self-practice</span></h2>
      <p className="muted" style={{ marginTop: 0 }}>Each task is a goal with random parameters and a rule that checks Laya’s answer. Practice runs use <b>real tools</b> (approval-gated tools are denied), so avoid tasks with side effects you don’t want.</p>

      <form onSubmit={save} className="taskform">
        <div className="grid g2">
          <label>Name<input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Miles to km" required maxLength={80} /></label>
          <label>Goal template<input value={form.template} onChange={(e) => set("template", e.target.value)} placeholder="Convert {a} miles to km" required maxLength={300} /></label>
        </div>
        <label>Parameters <span className="hint">one per line: <code>a: int 1..50</code> · <code>x: float 0.5..9.5</code> · <code>op: choice + | - | *</code></span>
          <textarea rows={3} value={form.params} onChange={(e) => set("params", e.target.value)} placeholder={"a: int 1..50"} /></label>
        <div className="grid g2">
          <label>How to check the answer
            <select value={form.check_type} onChange={(e) => set("check_type", e.target.value)}>{Object.entries(CHECKS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
          {form.check_type !== "succeeds" && <label>Check value<input value={form.check_value} onChange={(e) => set("check_value", e.target.value)} placeholder={c.placeholder} required /></label>}
        </div>
        {form.check_type === "expr" && <label style={{ maxWidth: 220 }}>Tolerance (relative)<input type="number" step="any" min={0} max={1} value={form.tolerance} onChange={(e) => set("tolerance", e.target.value)} /></label>}
        <p className="hint">{c.help}</p>
        {error && <p className="err" role="alert">{error}</p>}
        <div className="row">
          <button className="primary">{editing ? "Save changes" : "Add task"}</button>
          {editing && <button type="button" onClick={() => { setEditing(null); setForm(EMPTY); setError(""); }}>Cancel</button>}
          <span className="grow" />
          <button type="button" onClick={starter} disabled={busy === "starter"}>Add starter tasks</button>
          <a className="btnlink" href="/api/practice/export" download="laya-practice-tasks.json">Export</a>
          <button type="button" onClick={() => setShowImport(!showImport)}>Import</button>
        </div>
      </form>
      {showImport && (
        <div style={{ marginTop: 10 }}>
          <textarea rows={5} style={{ width: "100%" }} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder='Paste exported JSON: [{"name": "...", "template": "...", ...}]' aria-label="Import JSON" />
          <button onClick={doImport} disabled={!importText.trim()}>Import tasks</button>
        </div>
      )}
      {msg && <p role="status" style={{ marginBottom: 0 }}>{msg}</p>}

      {tasks && !tasks.length && <div className="empty">No custom tasks yet. Add one above or use the starter tasks.</div>}
      {!!tasks?.length && (
        <table style={{ marginTop: 12 }}>
          <thead><tr><th>On</th><th>Task</th><th>Check</th><th>Pass rate</th><th /></tr></thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id} style={{ opacity: t.enabled ? 1 : 0.55 }}>
                <td><input type="checkbox" checked={!!t.enabled} aria-label={`Include ${t.name} in practice`} onChange={(e) => api.patch(`/api/practice/tasks/${t.id}`, { enabled: e.target.checked }).then(reload)} /></td>
                <td><b>{t.name}</b><div className="mono muted">{t.template}</div>{t.last_fail && <div className="err" style={{ fontSize: 12 }}>last miss: {t.last_fail}</div>}</td>
                <td className="mono">{t.check_type}{t.check_value ? `: ${t.check_value}` : ""}</td>
                <td>{t.runs ? `${pct(t.pass_rate)} (${t.passes}/${t.runs})` : "—"}</td>
                <td className="row">
                  <button disabled={busy === t.id} onClick={() => run(t, 1)}>{busy === t.id ? "Running…" : "Test"}</button>
                  <button disabled={busy === t.id} onClick={() => run(t, 5)}>Run ×5</button>
                  <button onClick={() => edit(t)}>Edit</button>
                  <button className="danger" onClick={() => confirm(`Delete “${t.name}”?`) && api.del(`/api/practice/tasks/${t.id}`).then(reload)} aria-label={`Delete ${t.name}`}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
