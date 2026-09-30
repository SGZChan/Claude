import { pct } from "../api";
import { BarChart, Kpi, LineChart } from "../charts";
import { api } from "../api";
import { useApi } from "../hooks";

const S1 = { key: "system_one_rate", label: "System One hit rate", color: "var(--series-1)" };
const S2 = { key: "success_rate", label: "Success rate", color: "var(--series-2)" };

export default function Overview() {
  const [d, , err] = useApi("/api/metrics/overview", 4000);
  const [today, reloadToday] = useApi<any>("/api/assistant/today", 5000);
  if (err) return <p className="err">{err}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const k = d.kpis;
  return (
    <>
      <h1>Overview</h1>
      <p className="sub">How Laya is doing and how much it has learned.</p>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="Runs today" value={k.runs_today} hint={`${k.runs_total} total`} />
        <Kpi label="Success rate" value={pct(k.success_rate)} />
        <Kpi label="System One hit rate" value={pct(k.system_one_rate)} hint="answered by learned skills" />
        <Kpi label="Avg latency" value={`${k.avg_latency}s`} />
        <Kpi label="Skills learned" value={k.skills_learned} />
        <Kpi label="Memory items" value={k.memory_size} />
        <Kpi label="Feedback" value={`👍 ${k.thumbs_up}  👎 ${k.thumbs_down}`} />
      </div>
      {today && (today.brief || today.todos || today.reminders) && (
        <div className="card today">
          <h2>Today</h2>
          {today.alerts?.length > 0 && <div role="alert" className="err">{today.alerts.map((a: any) => <div key={a.id}>⏰ {a.text.replace("REMINDER: ", "")}</div>)}</div>}
          {today.brief && <p className="muted" style={{ marginTop: 0 }}>{today.brief}</p>}
          <div className="grid g2">
            {today.todos && <div><b>Open todos</b>{today.todos.length ? <ul>{today.todos.map((t: any) => <li key={t.id}>{t.text} <button className="link" onClick={() => api.post(`/api/todos/${t.id}/done`).then(reloadToday)}>done</button></li>)}</ul> : <p className="muted">All clear 🎉</p>}</div>}
            {today.reminders && <div><b>Reminders</b>{today.reminders.length ? <ul>{today.reminders.map((r: any) => <li key={r.id}>{r.text} <span className="muted">· {r.when}</span></li>)}</ul> : <p className="muted">None pending.</p>}</div>}
          </div>
        </div>
      )}
      <div className="card">
        <h2>Learning curve <span className="muted">— per 5 runs</span></h2>
        {d.learning_curve.length ? <LineChart data={d.learning_curve} x="upto_run" series={[S1, S2]} format={pct} yMax={1} /> : <div className="empty">No runs yet — try the Run console.</div>}
      </div>
      <div className="grid g2">
        <div className="card"><h2>Runs per day</h2><BarChart data={d.daily} x="date" y="runs" color="var(--series-1)" /></div>
        <div className="card"><h2>Daily success &amp; System One rate</h2><LineChart data={d.daily} x="date" series={[S1, S2]} format={pct} yMax={1} height={160} /></div>
      </div>
    </>
  );
}
