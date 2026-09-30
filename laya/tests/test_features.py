import json
import subprocess
import time
import zipfile
import io

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app
from laya.features import CATALOG, PRESETS
from laya.scheduler import Scheduler
from laya.tools.registry import ToolError


def call(laya, tool, **args):
    return laya.registry.call(tool, args)


def ws(laya, name, text):
    p = laya.settings.workspace / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


# ---------------------------------------------------------------- manager
def test_catalog_is_consistent(laya):
    ids = {f.id for f in CATALOG}
    assert len(ids) == len(CATALOG)
    for f in CATALOG:
        assert all(r in ids for r in f.requires)
    for name, pr in PRESETS.items():
        assert set(pr["features"]) <= ids, name
    # every tool belongs to a known feature, and every tool-feature has tools
    tool_feats = {t.feature for t in laya.registry.tools.values()}
    assert tool_feats <= ids | {"plugins"}
    for f in CATALOG:
        if f.kind == "tools" and f.id != "plugins":
            assert f.id in tool_feats, f"{f.id} has no tools"


def test_toggle_hides_and_blocks_tools(laya):
    assert "todo_add" in laya.registry.prompt_block()
    laya.features.set_enabled("todos", False)
    assert "todo_add" not in laya.registry.prompt_block()
    with pytest.raises(ToolError, match="disabled"):
        call(laya, "todo_add", text="x")
    laya.features.set_enabled("todos", True)
    assert "added todo" in call(laya, "todo_add", text="x")


def test_state_persists_across_restart(laya):
    from laya.core import Laya
    laya.features.set_enabled("journal", False)
    again = Laya(laya.settings, llm=laya.llm)
    assert not again.features.enabled("journal") and again.features.enabled("todos")


def test_dependencies_cascade(laya):
    laya.features.set_enabled("watch_folder", True)
    assert laya.features.enabled("knowledge_base")          # pulled in
    laya.features.set_enabled("knowledge_base", False)
    assert not laya.features.enabled("watch_folder")        # dependent switched off
    with pytest.raises(Exception):
        laya.features.set_enabled("nope", True)


def test_presets(laya):
    laya.features.apply_preset("minimal")
    assert laya.features.enabled("notes") and not laya.features.enabled("todos")
    laya.features.apply_preset("private")
    assert laya.features.enabled("offline_mode") and not laya.features.enabled("web_digest")
    laya.features.apply_preset("everything")
    assert all(laya.features.enabled(f.id) for f in CATALOG)


def test_offline_mode_blocks_network_tools(laya, monkeypatch):
    laya.features.set_enabled("web_digest", True)
    laya.features.set_enabled("offline_mode", True)
    with pytest.raises(ToolError, match="offline"):
        call(laya, "web_fetch", url="https://en.wikipedia.org/")
    assert "web_fetch" not in laya.registry.prompt_block()
    listed = {f["id"]: f for f in laya.features.list()}
    assert listed["web_digest"]["blocked_by_offline"] is True


def test_tool_prompt_is_limited_to_relevant_tools(laya):
    laya.features.apply_preset("everything")
    block = laya.registry.prompt_block("convert 5 miles to km", k=8)
    assert len(block.splitlines()) == 8 and "unit_convert" in block


# ---------------------------------------------------------------- assistant
def test_todos(laya):
    call(laya, "todo_add", text="buy milk")
    call(laya, "todo_add", text="call mum", due="friday")
    assert "#1 buy milk" in call(laya, "todo_list") and "due friday" in call(laya, "todo_list")
    call(laya, "todo_done", id="#1")
    assert "buy milk" not in call(laya, "todo_list")
    with pytest.raises(ToolError):
        call(laya, "todo_done", id="1")


def test_parse_when():
    from laya.tools.assistant import parse_when
    now = time.time()
    assert abs(parse_when("in 30 minutes", now) - (now + 1800)) < 1
    assert abs(parse_when("in 2 hours", now) - now - 7200) < 1
    assert parse_when("tomorrow 14:30", now) > now
    assert parse_when("2030-01-02 08:15") > now
    with pytest.raises(ToolError):
        parse_when("whenever")


def test_reminders_and_job(laya):
    call(laya, "reminder_add", text="stretch", when="in 30 minutes")
    assert "stretch" in call(laya, "reminder_list")
    assert laya.features.run_job("reminders", force=True) == "fired 0 reminder(s)"
    laya.store.x("UPDATE reminders SET due=?", (time.time() - 5,))
    assert laya.features.run_job("reminders", force=True) == "fired 1 reminder(s)"
    assert "pending" in call(laya, "reminder_list") or "no pending" in call(laya, "reminder_list")
    assert laya.store.list_facts("reminder")


def test_daily_brief_and_auto_brief_job(laya):
    call(laya, "todo_add", text="write report")
    call(laya, "notes_add", text="dentist at 3")
    b = call(laya, "daily_brief")
    assert "write report" in b and "dentist at 3" in b
    laya.features.set_enabled("auto_brief", True)
    assert laya.features.run_job("auto_brief", force=True) == "brief generated"
    assert laya.features.run_job("auto_brief", force=True) == "already generated today"
    assert laya.store.list_facts("brief")


def test_journal(laya):
    call(laya, "journal_add", text="hiked up the mountain today", mood="happy")
    call(laya, "journal_add", text="tax paperwork was boring")
    assert "mountain" in call(laya, "journal_search", query="hiking mountain")


def test_calendar(laya):
    laya.features.set_enabled("calendar", True)
    soon = time.strftime("%Y%m%dT%H%M00", time.localtime(time.time() + 3600))
    later = time.strftime("%Y%m%dT%H%M00", time.localtime(time.time() + 40 * 86400))
    ws(laya, "cal.ics", f"BEGIN:VEVENT\nSUMMARY:Dentist\nDTSTART:{soon}\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:Far away\nDTSTART:{later}\nEND:VEVENT")
    out = call(laya, "calendar_upcoming", days="7")
    assert "Dentist" in out and "Far away" not in out


# ---------------------------------------------------------------- files / data
def test_file_helper_tools(laya):
    ws(laya, "notes.txt", "Laya is a local assistant. It learns skills from repeated success. Contact bob@example.com or visit https://example.org/docs. "
       "The budget is 1200 dollars, due 2026-12-01. Skills make repeated tasks fast because skills skip the model.")
    assert "notes.txt:1" in call(laya, "file_search", query="LOCAL assistant")
    assert "skills" in call(laya, "file_summarize", path="notes.txt").lower()
    assert call(laya, "file_extract", path="notes.txt", kind="emails") == "bob@example.com"
    assert "2026-12-01" in call(laya, "file_extract", path="notes.txt", kind="dates")
    assert "words" in call(laya, "file_stats", path="notes.txt")
    with pytest.raises(ToolError):
        call(laya, "file_extract", path="notes.txt", kind="colors")
    with pytest.raises(ToolError):
        call(laya, "file_read", path="../../etc/passwd")


CSV = "region,amount,item\nnorth,100,pen\nsouth,250,book\nnorth,50,cap\nwest,abc,x\n"


def test_data_wrangling(laya):
    ws(laya, "sales.csv", CSV)
    assert "4 rows" in call(laya, "csv_head", path="sales.csv")
    stats = call(laya, "csv_stats", path="sales.csv", column="amount")
    assert "count=3" in stats and "max=250" in stats and "sum=400" in stats
    assert call(laya, "csv_filter", path="sales.csv", column="amount", op=">", value="60").startswith("2 of 4")
    assert call(laya, "csv_filter", path="sales.csv", column="item", op="contains", value="BO").startswith("1 of 4")
    assert call(laya, "csv_group", path="sales.csv", column="region").startswith("north: 2")
    assert call(laya, "csv_group", path="sales.csv", column="region", sum_column="amount").startswith("south: 250")
    with pytest.raises(ToolError, match="no column"):
        call(laya, "csv_stats", path="sales.csv", column="nope")
    ws(laya, "d.json", json.dumps({"a": {"b": [1, {"c": "hit"}]}}))
    assert call(laya, "json_query", path="d.json", query="a.b[1].c") == '"hit"'
    with pytest.raises(ToolError):
        call(laya, "json_query", path="d.json", query="a.zzz")


# ---------------------------------------------------------------- dev
def test_dev_helper(laya):
    ws(laya, "app.py", "def hello():\n    return 1\n")
    assert "app.py:1" in call(laya, "repo_search", pattern=r"def \w+")
    with pytest.raises(ToolError):
        call(laya, "repo_search", pattern="(")
    w = laya.settings.workspace
    subprocess.run(["git", "init", "-q", str(w)], check=True)
    subprocess.run(["git", "-C", str(w), "-c", "user.email=a@b.c", "-c", "user.name=t", "add", "."], check=True)
    subprocess.run(["git", "-C", str(w), "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-qm", "first"], check=True)
    assert "first" in call(laya, "git_log", n="3")
    assert "##" in call(laya, "git_status")
    ws(laya, "app.py", "def hello():\n    return 2\n")
    assert "app.py" in call(laya, "git_diff")
    with pytest.raises(ToolError, match="not allowed"):
        call(laya, "run_tests", command="rm -rf /")
    assert laya.registry.get("run_tests").tier == "confirm"


def test_code_sandbox_needs_feature_and_approval(laya):
    with pytest.raises(ToolError, match="disabled"):
        call(laya, "python_sandbox", code="print(1)")
    laya.features.set_enabled("code_sandbox", True)
    assert call(laya, "python_sandbox", code="print(2**10)").strip() == "1024"
    with pytest.raises(ToolError):
        call(laya, "shell_readonly", command="rm x")
    r = laya.agent.run("Run python: print(3)")   # confirm tier without approver -> denied
    assert r["steps"][0]["ok"] is False and "denied" in r["steps"][0]["result"]


# ---------------------------------------------------------------- comms
def test_triage(laya):
    assert "category=urgent priority=3/3" in call(laya, "triage_text", text="URGENT: please send it asap")
    assert "category=meeting" in call(laya, "triage_text", text="Can we schedule a call on the calendar? Zoom invite attached")
    assert "category=invoice" in call(laya, "triage_text", text="Your invoice is overdue, payment needed")
    assert "category=spam priority=1" not in call(laya, "triage_text", text="You are a winner! click here for free money, act now")
    assert "category=newsletter" in call(laya, "triage_text", text="Weekly digest. Unsubscribe here")
    assert "deadline: friday" in call(laya, "triage_text", text="Please review by friday")
    assert "time options" in call(laya, "draft_reply", text="Let's schedule a meeting call")
    assert call(laya, "draft_reply", text="Weekly digest unsubscribe").startswith("No reply needed")
    assert call(laya, "draft_reply", text="asap!", tone="formal").startswith("Dear Sir")


def test_triage_inbox(laya):
    ws(laya, "mail/a.eml", "From: boss@x.com\nSubject: URGENT budget\n\nSend the numbers asap.\n")
    ws(laya, "mail/b.eml", "From: news@x.com\nSubject: Weekly digest\n\nUnsubscribe anytime\n")
    out = call(laya, "triage_inbox", path="mail").splitlines()
    assert "urgent" in out[0] and "newsletter" in out[1]
    (laya.settings.workspace / "empty").mkdir()
    with pytest.raises(ToolError, match="no .eml"):
        call(laya, "triage_inbox", path="empty")
