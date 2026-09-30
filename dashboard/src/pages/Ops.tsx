import { useState } from "react";
import { api, ago } from "../api";
import { useApi } from "../hooks";

export function Tools() {
  const [tools, reload] = useApi<any[]>("/api/tools", 5000);
  return (
    <>
      <h1>Tools &amp; permissions</h1>
      <p className="sub"><b>safe</b> runs freely · <b>confirm</b> asks you first · <b>blocked</b> is unavailable.</p>
      <div className="card">
        <table>
          <thead><tr><th>Tool</th><th>Description</th><th>Calls</th><th>Errors</th><th>Permission</th></tr></thead>
          <tbody>
            {tools?.map((t) => (
              <tr key={t.name}>
                <td className="mono">{t.name}({Object.keys(t.params).join(", ")})</td><td>{t.description}</td><td>{t.calls}</td><td>{t.errors}</td>
                <td><select value={t.tier} aria-label={`Permission for ${t.name}`} onChange={(e) => api.patch(`/api/tools/${t.name}`, { tier: e.target.value }).then(reload)}>
                  {["safe", "confirm", "blocked"].map((x) => <option key={x}>{x}</option>)}
                </select></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Schedules() {
  const [list, reload] = useApi<any[]>("/api/schedules", 5000);
  const [goal, setGoal] = useState("");
  const [mins, setMins] = useState(60);
  return (
    <>
      <h1>Schedules</h1>
      <p className="sub">Recurring goals. Learned skills make repeat runs nearly free.</p>
      <div className="card">
        <form className="row" style={{ marginBottom: 12 }} onSubmit={(e) => { e.preventDefault(); if (goal.trim()) api.post("/api/schedules", { goal, interval_s: mins * 60 }).then(() => { setGoal(""); reload(); }); }}>
          <input className="grow" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Goal to run, e.g. What time is it" aria-label="Scheduled goal" />
          <label>every <input type="number" min={1} value={mins} onChange={(e) => setMins(Math.max(1, +e.target.value))} style={{ width: 70 }} /> min</label>
          <button className="primary">Add</button>
        </form>
        {list && !list.length && <div className="empty">No schedules.</div>}
        {!!list?.length && (
          <table>
            <thead><tr><th>Goal</th><th>Every</th><th>Last run</th><th /></tr></thead>
            <tbody>{list.map((s) => (
              <tr key={s.id}>
                <td>{s.goal}</td><td>{Math.round(s.interval_s / 60)} min</td><td className="muted">{ago(s.last_run)}</td>
                <td className="row">
                  <button onClick={() => api.patch(`/api/schedules/${s.id}`, { enabled: !s.enabled }).then(reload)}>{s.enabled ? "Pause" : "Resume"}</button>
                  <button className="danger" onClick={() => api.del(`/api/schedules/${s.id}`).then(reload)}>Delete</button>
                </td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
    </>
  );
}

export function System({ sys }: { sys: any }) {
  if (!sys) return <p className="muted">Loading…</p>;
  const rows: [string, string][] = [
    ["Backend", sys.llm.backend], ["Model", sys.llm.model], ["Throughput", sys.llm.tokens_per_sec ? `${sys.llm.tokens_per_sec} tokens/s` : "n/a"],
    ["Step budget", String(sys.max_steps)], ["Time budget", `${sys.run_timeout}s`], ["Skill promotion threshold", `${sys.promote_after} successes`],
    ["Web allow-list", sys.web_allowlist.join(", ") || "(none)"], ["Data directory", sys.data_dir], ["Version", sys.version],
  ];
  return (
    <>
      <h1>System</h1>
      <p className="sub">Runtime configuration (edit via environment variables, see .env.example).</p>
      {sys.llm.backend === "mock" && <div className="card">⚠ Running on the scripted <b>mock</b> model. Run <span className="mono">python scripts/download_model.py</span> to install the real 0.5B model.</div>}
      <div className="card"><table><tbody>{rows.map(([k, v]) => <tr key={k}><th>{k}</th><td className="mono">{v}</td></tr>)}</tbody></table></div>
    </>
  );
}
