import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app
from laya.scheduler import Scheduler
from laya.tools.registry import ToolError


def call(laya, tool, **args):
    return laya.registry.call(tool, args)


def ws(laya, name, text):
    p = laya.settings.workspace / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


# ---------------------------------------------------------------- utilities
def test_unit_convert_and_dates(laya):
    assert call(laya, "unit_convert", value="5", from_unit="miles", to_unit="km").startswith("8.04672")
    assert call(laya, "unit_convert", value="100", from_unit="c", to_unit="f") == "212 f"
    assert call(laya, "unit_convert", value="1", from_unit="gb", to_unit="mb") == "1000 mb"
    with pytest.raises(ToolError):
        call(laya, "unit_convert", value="1", from_unit="kg", to_unit="km")
    assert call(laya, "date_math", start="2026-01-31", days="1") == "2026-02-01 (Sunday)"
    assert call(laya, "date_diff", a="2026-01-01", b="2026-03-01") == "59 days"
    with pytest.raises(ToolError):
        call(laya, "date_math", start="31/01/2026", days="1")


def test_password_tools(laya):
    a, b = call(laya, "password_gen", length="20"), call(laya, "password_gen", length="20")
    assert len(a) == 20 and a != b
    assert len(call(laya, "password_gen", length="2")) == 8            # clamped to a safe minimum
    pp = call(laya, "passphrase", words="5")
    assert pp.count("-") == 4 and "bits" in pp
    assert "words" in call(laya, "text_stats", text="One two three. Four five!")


# ---------------------------------------------------------------- knowledge base
def test_knowledge_base_ingest_ask_update(laya):
    ws(laya, "docs/plan.md", "The launch deadline is March 3rd.\n\nBudget owner is Priya.\n\nBanana bread recipe uses three ripe bananas.")
    assert "1 new" in call(laya, "kb_ingest")
    assert "0 new and 0 updated" in call(laya, "kb_ingest")             # unchanged files are skipped
    assert "docs/plan.md" in call(laya, "kb_ask", question="who owns the budget") and "Priya" in call(laya, "kb_ask", question="who owns the budget")
    assert "plan.md" in call(laya, "kb_sources")
    time.sleep(0.02)
    ws(laya, "docs/plan.md", "The launch deadline moved to April 9th.")
    p = laya.settings.workspace / "docs/plan.md"
    import os
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert "1 updated" in call(laya, "kb_ingest")
    assert "April" in call(laya, "kb_ask", question="launch deadline")
    assert "Priya" not in call(laya, "kb_ask", question="launch deadline")   # stale chunks removed
    with pytest.raises(ToolError):
        call(laya, "kb_ask", question="xylophone symphony orchestra")


def test_watch_folder_job(laya):
    laya.features.set_enabled("watch_folder", True)
    ws(laya, "a.txt", "Alpha project notes about penguins and icebergs.")
    assert "1 new" in laya.features.run_job("watch_folder", force=True)
    assert "penguins" in call(laya, "kb_ask", question="penguins")


# ---------------------------------------------------------------- web
def test_web_digest_allowlist_and_summary(laya, monkeypatch):
    laya.features.set_enabled("web_digest", True)
    html = "<html><script>bad()</script><body><p>Llamas are domesticated South American camelids. They are widely used as pack animals by Andean cultures.</p>" \
           "<p>Llamas can carry loads of about a quarter of their body weight over long distances.</p></body></html>"
    import laya.tools.web as web
    monkeypatch.setattr(web.urllib.request, "urlopen", lambda url, timeout=0: io.BytesIO(html.encode()))
    out = call(laya, "web_digest", url="https://en.wikipedia.org/wiki/Llama")
    assert "Llamas" in out and "bad()" not in out
    assert laya.store.list_facts("digest")
    with pytest.raises(ToolError, match="allow-listed"):
        call(laya, "web_digest", url="https://evil.example.com/x")
    with pytest.raises(ToolError, match="allow-listed"):
        call(laya, "web_fetch", url="http://en.wikipedia.org/x")     # http, not https


# ---------------------------------------------------------------- plugins
def test_plugins(laya):
    assert laya.features.plugins() == []
    laya.features.set_enabled("plugins", True)
    ps = laya.features.plugins()
    assert ps[0]["ok"] and "hello_plugin" in ps[0]["tools"]
    assert laya.registry.get("hello_plugin").tier == "confirm"
    assert call(laya, "hello_plugin", name="Ash") == "Hello, Ash! (from a plugin)"
    (laya.settings.data_dir / "plugins" / "broken.py").write_text("raise RuntimeError('boom')")
    (laya.settings.data_dir / "plugins" / "nofn.py").write_text("x = 1")
    res = {p["file"]: p for p in laya.features.plugins()}
    assert res["broken.py"]["ok"] is False and "boom" in res["broken.py"]["error"]
    assert res["nofn.py"]["ok"] is False
    assert res["hello_plugin.py"]["ok"]                                   # one bad plugin doesn't stop the rest
    laya.features.set_enabled("plugins", False)
    with pytest.raises(ToolError, match="disabled"):
        call(laya, "hello_plugin", name="x")


# ---------------------------------------------------------------- learning toggles
def test_system_one_off_never_uses_skills(laya):
    for a in (2, 3, 4):
        laya.agent.run(f"What is {a}*{a}?")
    assert laya.agent.run("What is 5*5?")["via"] == "skill"
    laya.features.set_enabled("system_one", False)
    assert laya.agent.run("What is 6*6?")["via"] == "agent"


def test_reflection_and_recall_toggles(laya):
    laya.features.set_enabled("reflection", False)
    laya.agent.run("What is 2*8?")
    assert not laya.store.list_facts("lesson")
    laya.features.set_enabled("reflection", True)
    laya.agent.run("What is 3*8?")
    assert laya.store.list_facts("lesson")
    seen = []
    orig = laya.llm.generate
    laya.llm.generate = lambda p, **k: (seen.append(p), orig(p, **k))[1]
    laya.agent.run("What is 4*8?")
    assert any("LESSONS:" in p for p in seen)
    seen.clear()
    laya.features.set_enabled("memory_recall", False)
    laya.agent.run("What is 5*8 and save it to notes")
    assert not any("LESSONS:" in p for p in seen)


def test_self_practice_job_and_scheduler(laya):
    laya.features.set_enabled("self_practice", True)
    sched = Scheduler(laya)
    res = sched.tick()
    assert "3/3 correct" in res["jobs"]["self_practice"]
    assert sched.tick()["jobs"].get("self_practice") is None              # interval not elapsed
    assert "self_practice" in sched.tick(now=time.time() + 4000)["jobs"]
    laya.store.set_kv("killed", "1")
    assert sched.tick(now=time.time() + 9000) == {"schedules": [], "jobs": {}}


def test_scheduler_respects_feature_toggle(laya):
    laya.store.x("INSERT INTO schedules(goal,interval_s,last_run) VALUES('What is 1+1?',60,0)")
    laya.features.set_enabled("scheduler", False)
    assert Scheduler(laya).tick()["schedules"] == []
    laya.features.set_enabled("scheduler", True)
    assert Scheduler(laya).tick()["schedules"] == [1]


# ---------------------------------------------------------------- agent end-to-end with the new tools
@pytest.mark.parametrize("goal,expect", [
    ("Add todo buy milk", "added todo #1"),
    ("Remind me to stretch in 30 minutes", "reminder #1 set"),
    ("Convert 5 miles to km", "8.04672"),
    ("How many days between 2026-01-01 and 2026-03-01", "59 days"),
    ("Give me my daily brief", "Today is"),
    ("Triage: URGENT send the invoice by friday", "category=urgent"),
    ("Generate a passphrase", "bits"),
    ("Journal: quiet productive morning", "journal entry saved"),
])
def test_agent_uses_new_tools(laya, goal, expect):
    r = laya.agent.run(goal)
    assert r["status"] == "ok" and expect in r["answer"], r


def test_agent_file_and_data_goals(laya):
    ws(laya, "sales.csv", "region,amount\nn,10\ns,30\n")
    ws(laya, "readme.txt", "Laya keeps everything local. Laya is private by design and never sends data anywhere unless you allow it.")
    assert "mean=20" in laya.agent.run("csv stats sales.csv amount")["answer"]
    assert "Laya" in laya.agent.run("Summarize readme.txt")["answer"]
    assert laya.agent.run("Ingest my documents")["status"] == "ok"
    assert "readme.txt" in laya.agent.run("What do my documents say about privacy")["answer"]


def test_disabled_feature_makes_agent_fail_cleanly(laya):
    laya.features.set_enabled("todos", False)
    r = laya.agent.run("Add todo buy milk")
    assert r["status"] == "failed" and "disabled" in r["steps"][0]["result"]


# ---------------------------------------------------------------- API
@pytest.fixture
def client(laya):
    return TestClient(create_app(laya))


def test_features_api(client, laya):
    d = client.get("/api/features").json()
    assert {f["id"] for f in d["features"]} >= {"todos", "knowledge_base", "plugins"}
    assert "Assistant" in d["categories"] and any(p["id"] == "private" for p in d["presets"])
    todos = next(f for f in d["features"] if f["id"] == "todos")
    assert todos["enabled"] and {t["name"] for t in todos["tools"]} == {"todo_add", "todo_list", "todo_done"}
    assert client.patch("/api/features/todos", json={"enabled": False}).json()["changed"] == ["todos"]
    assert not laya.features.enabled("todos")
    assert client.patch("/api/features/nope", json={"enabled": True}).status_code == 404
    assert "offline_mode" in client.post("/api/features/preset/private").json()["enabled"]
    assert client.post("/api/features/preset/nope").status_code == 404
    tools = {t["name"]: t for t in client.get("/api/tools").json()}
    assert tools["web_fetch"]["available"] is False


def test_job_run_endpoint_and_last_result(client, laya):
    assert client.post("/api/features/self_practice/run").status_code == 409         # off by default
    client.patch("/api/features/reminders", json={"enabled": True})
    assert client.post("/api/features/reminders/run").json()["message"].startswith("fired")
    rem = next(f for f in client.get("/api/features").json()["features"] if f["id"] == "reminders")
    assert rem["job"]["last"]["ok"] is True


def test_backup_and_today_and_plugins_api(client, laya):
    ws(laya, "keep.txt", "hello")
    client.post("/api/runs", json={"goal": "Add todo call bank"})
    for _ in range(50):
        if laya.store.q("SELECT * FROM todos"):
            break
        time.sleep(0.05)
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/backup.zip").content))
    assert {"laya.db", "workspace/keep.txt"} <= set(z.namelist())
    t = client.get("/api/assistant/today").json()
    assert t["todos"][0]["text"] == "call bank" and "Today is" in t["brief"]
    client.post(f"/api/todos/{t['todos'][0]['id']}/done")
    assert client.get("/api/assistant/today").json()["todos"] == []
    client.patch("/api/features/backup", json={"enabled": False})
    assert client.get("/api/backup.zip").status_code == 403
    client.patch("/api/features/todos", json={"enabled": False})
    assert client.get("/api/assistant/today").json()["todos"] is None
    assert client.get("/api/plugins").json()["enabled"] is False
    client.patch("/api/features/plugins", json={"enabled": True})
    assert client.get("/api/plugins").json()["plugins"][0]["ok"]
