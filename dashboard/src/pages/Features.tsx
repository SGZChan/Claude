import { useMemo, useState } from "react";
import { api, ago } from "../api";
import { useApi } from "../hooks";

const RISK: Record<string, string> = { low: "Low risk", medium: "Touches files/network", high: "High risk" };
const KIND: Record<string, string> = { tools: "Tools", policy: "Policy", behaviour: "Behaviour", job: "Background job" };

export default function Features() {
  const [data, reload, err] = useApi<any>("/api/features", 4000);
  const [plugins, reloadPlugins] = useApi<any>("/api/plugins");
  const [q, setQ] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const feats: any[] = data?.features ?? [];
  const byId = useMemo(() => Object.fromEntries(feats.map((f) => [f.id, f])), [feats]);
  const shown = feats.filter((f) => !q || `${f.name} ${f.description} ${f.category} ${f.tools.map((t: any) => t.name).join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  const on = feats.filter((f) => f.enabled).length;

  const toggle = async (f: any) => {
    setBusy(f.id);
    try {
      const { changed } = await api.patch(`/api/features/${f.id}`, { enabled: !f.enabled });
      const others = changed.filter((c: string) => c !== f.id).map((c: string) => byId[c]?.name ?? c);
      setNotice(others.length ? `${f.enabled ? "Also turned off" : "Also turned on"}: ${others.join(", ")}` : "");
      reload(); reloadPlugins();
    } catch (e: any) { setNotice(e.message); } finally { setBusy(""); }
  };
  const preset = async (p: any) => {
    if (!confirm(`Apply the “${p.label}” preset? This replaces your current feature choices (${p.count} features on).`)) return;
    await api.post(`/api/features/preset/${p.id}`); setNotice(`Applied “${p.label}”.`); reload(); reloadPlugins();
  };
  const runJob = async (f: any) => {
    try { const r = await api.post(`/api/features/${f.id}/run`); setNotice(`${f.name}: ${r.message}`); reload(); } catch (e: any) { setNotice(e.message); }
  };

  if (err) return <p className="err">{err}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>Features</h1>
      <p className="sub">Choose what Laya can do. Turned-off features are removed from the model’s tool list and refuse to run. <b>{on}</b> of {feats.length} on.</p>

      <div className="card">
        <h2>Presets</h2>
        <div className="row">
          {data.presets.map((p: any) => (
            <button key={p.id} onClick={() => preset(p)} title={p.description}>{p.label} <span className="muted">· {p.count}</span></button>
          ))}
        </div>
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input className="grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search features and tools" aria-label="Search features" />
      </div>
      {notice && <div className="card" role="status" style={{ padding: 10 }}>{notice} <button style={{ float: "right" }} onClick={() => setNotice("")} aria-label="Dismiss">✕</button></div>}

      {data.categories.map((cat: string) => {
        const items = shown.filter((f) => f.category === cat);
        if (!items.length) return null;
        return (
          <section key={cat}>
            <h2 className="cat">{cat}</h2>
            <div className="grid g2">
              {items.map((f) => (
                <div key={f.id} className={`card feat ${f.enabled ? "on" : "off"}`} style={{ marginBottom: 0 }}>
                  <div className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                    <div>
                      <b>{f.name}</b>
                      <div className="row" style={{ gap: 6, marginTop: 4 }}>
                        <span className={`badge risk-${f.risk}`}>{RISK[f.risk]}</span>
                        <span className="badge">{KIND[f.kind]}</span>
                      </div>
                    </div>
                    <button role="switch" aria-checked={f.enabled} aria-label={`${f.name}: ${f.enabled ? "on" : "off"}`}
                      className={`switch ${f.enabled ? "checked" : ""}`} disabled={busy === f.id} onClick={() => toggle(f)}><span /></button>
                  </div>
                  <p className="muted" style={{ margin: "8px 0" }}>{f.description}</p>
                  {f.blocked_by_offline && <p className="err">🌐 Blocked by Offline mode.</p>}
                  {!!f.requires.length && <p className="hint">Needs: {f.requires.map((r: string) => byId[r]?.name ?? r).join(", ")}</p>}
                  {!!f.tools.length && (
                    <div className="chips">
                      {f.tools.map((t: any) => <span key={t.name} className="chip mono" title={t.tier === "confirm" ? "Asks for your approval each time" : t.network ? "Uses the network" : "Runs freely"}>
                        {t.tier === "confirm" ? "🔒 " : t.network ? "🌐 " : ""}{t.name}</span>)}
                    </div>
                  )}
                  {f.job && (
                    <p className="hint">
                      Runs every {f.job.interval >= 60 ? `${Math.round(f.job.interval / 60)} min` : `${f.job.interval}s`} ·{" "}
                      {f.job.last ? <>last {ago(f.job.last.ts)}: {f.job.last.ok ? f.job.last.message : <span className="err">{f.job.last.message}</span>}</> : "not run yet"}
                      {f.enabled && <> · <button className="link" onClick={() => runJob(f)}>Run now</button></>}
                    </p>
                  )}
                  {f.id === "backup" && f.enabled && <a className="btnlink" href="/api/backup.zip">Download backup (.zip)</a>}
                  {f.id === "plugins" && f.enabled && plugins && (
                    <div className="hint">
                      Folder: <span className="mono">{plugins.dir}</span>
                      {plugins.plugins.map((p: any) => <div key={p.file}>{p.ok ? "✓" : "✕"} <span className="mono">{p.file}</span> {p.ok ? `→ ${p.tools.join(", ") || "no tools"}` : <span className="err">{p.error}</span>}</div>)}
                    </div>
                  )}
                  {f.example && f.enabled && <a className="tryit" href={`#/console?goal=${encodeURIComponent(f.example)}`}>Try: “{f.example}”</a>}
                </div>
              ))}
            </div>
          </section>
        );
      })}
      {!shown.length && <div className="empty">No features match “{q}”.</div>}
    </>
  );
}
