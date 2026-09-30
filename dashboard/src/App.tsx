import { useEffect, useState } from "react";
import { api } from "./api";
import { useApi } from "./hooks";
import Overview from "./pages/Overview";
import Console from "./pages/Console";
import { Runs, RunDetail } from "./pages/Runs";
import { Skills, Memory, Learning } from "./pages/Knowledge";
import { Tools, Schedules, System } from "./pages/Ops";

const NAV: [string, string][] = [
  ["", "Overview"], ["console", "Run console"], ["runs", "Runs"], ["skills", "Skills"], ["memory", "Memory"],
  ["learning", "Learning"], ["tools", "Tools"], ["schedules", "Schedules"], ["system", "System"],
];

const useHash = () => {
  const [h, setH] = useState(location.hash.slice(2));
  useEffect(() => { const f = () => setH(location.hash.slice(2)); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
};

export default function App() {
  const hash = useHash();
  const [page, arg] = hash.split("/");
  const [sys, reloadSys] = useApi("/api/system", 5000);
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem("laya-theme") || ""; } catch { return ""; } });
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
    try { theme ? localStorage.setItem("laya-theme", theme) : localStorage.removeItem("laya-theme"); } catch { /* storage unavailable */ }
  }, [theme]);
  const killed = !!sys?.killed;
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">Laya<small>System One AI</small></div>
        <nav>{NAV.map(([p, l]) => <a key={p} href={`#/${p}`} className={page === p ? "on" : ""}>{l}</a>)}</nav>
        <div className="foot">
          <div className="muted" style={{ fontSize: 12 }}>{sys ? `${sys.llm.model}${sys.llm.tokens_per_sec ? ` · ${sys.llm.tokens_per_sec} tok/s` : ""}` : "connecting…"}</div>
          <button className={killed ? "primary" : "danger"} onClick={() => api.post("/api/system/kill", { on: !killed }).then(reloadSys)}>
            {killed ? "Resume Laya" : "Kill switch"}
          </button>
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "Light theme" : "Dark theme"}</button>
        </div>
      </aside>
      <main>
        {killed && <div className="card err" role="alert">⛔ Kill switch is ON — Laya will not run new goals.</div>}
        {page === "" && <Overview />}
        {page === "console" && <Console killed={killed} />}
        {page === "runs" && (arg ? <RunDetail id={+arg} /> : <Runs />)}
        {page === "skills" && <Skills />}
        {page === "memory" && <Memory />}
        {page === "learning" && <Learning />}
        {page === "tools" && <Tools />}
        {page === "schedules" && <Schedules />}
        {page === "system" && <System sys={sys} />}
      </main>
    </div>
  );
}
