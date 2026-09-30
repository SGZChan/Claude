"""Personal-assistant features: todos, reminders, journal, daily brief, calendar."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from .helpers import Ctx, read_text
from .registry import ToolError


def parse_when(s: str, now: float | None = None) -> float:
    now_dt = datetime.fromtimestamp(now or time.time())
    s = str(s).strip().lower()
    if m := re.fullmatch(r"in (\d+)\s*(min|mins|minute|minutes|hour|hours|h|day|days|d)", s):
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(minutes=n) if unit.startswith("m") else timedelta(hours=n) if unit.startswith("h") else timedelta(days=n)
        return (now_dt + delta).timestamp()
    if m := re.fullmatch(r"(today|tomorrow)(?:\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?)?", s):
        base = now_dt + timedelta(days=1 if m.group(1) == "tomorrow" else 0)
        return base.replace(hour=int(m.group(2) or 9), minute=int(m.group(3) or 0), second=0, microsecond=0).timestamp()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    raise ToolError("could not understand time; use 'in 30 minutes', 'tomorrow 9:00' or 'YYYY-MM-DD HH:MM'")


def fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def brief_text(store) -> str:
    now = time.time()
    todos = store.q("SELECT id,text,due FROM todos WHERE done=0 ORDER BY id LIMIT 5")
    rem = store.q("SELECT text,due FROM reminders WHERE fired=0 AND due<=? ORDER BY due LIMIT 5", (now + 86400,))
    notes = store.q("SELECT text FROM notes ORDER BY id DESC LIMIT 3")
    day0 = now - (now % 86400)
    runs = store.q("SELECT COUNT(*) c, SUM(via='skill') s FROM runs WHERE started>=?", (day0,))[0]
    parts = [f"Today is {time.strftime('%A %Y-%m-%d %H:%M')}."]
    parts.append("Open todos: " + ("; ".join(f"#{t['id']} {t['text']}" for t in todos) if todos else "none") + ".")
    parts.append("Reminders next 24h: " + ("; ".join(f"{r['text']} ({fmt_ts(r['due'])})" for r in rem) if rem else "none") + ".")
    if notes:
        parts.append("Recent notes: " + "; ".join(n["text"] for n in notes) + ".")
    parts.append(f"Laya handled {runs['c'] or 0} runs today ({runs['s'] or 0} via skills).")
    return " ".join(parts)


def ics_events(text: str) -> list[tuple[float, str]]:
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        s = re.search(r"SUMMARY[^:]*:(.*)", block)
        d = re.search(r"DTSTART[^:]*:(\d{8})(?:T(\d{4}))?", block)
        if not (s and d):
            continue
        hhmm = d.group(2) or "0000"
        try:
            ts = datetime.strptime(d.group(1) + hhmm, "%Y%m%d%H%M").timestamp()
        except ValueError:
            continue
        out.append((ts, s.group(1).strip()))
    return out


def install(ctx: Ctx) -> None:
    reg, store = ctx.reg, ctx.store

    @reg.register("todo_add", "add a to-do item", {"text": "task", "due": "optional due date"}, feature="todos", optional=("due",))
    def todo_add(text: str, due: str = "") -> str:
        tid = store.x("INSERT INTO todos(text,due,created) VALUES(?,?,?)", (str(text)[:300], str(due), time.time()))
        return f"added todo #{tid}: {text}"

    @reg.register("todo_list", "list open to-do items (tasks)", {}, feature="todos")
    def todo_list() -> str:
        rows = store.q("SELECT id,text,due FROM todos WHERE done=0 ORDER BY id")
        return "; ".join(f"#{r['id']} {r['text']}" + (f" (due {r['due']})" if r["due"] else "") for r in rows) or "no open todos"

    @reg.register("todo_done", "mark a to-do as done", {"id": "todo number"}, feature="todos")
    def todo_done(id: str) -> str:  # noqa: A002
        tid = int(str(id).lstrip("#"))
        if not store.q("SELECT id FROM todos WHERE id=? AND done=0", (tid,)):
            raise ToolError("no such open todo")
        store.x("UPDATE todos SET done=1 WHERE id=?", (tid,))
        return f"todo #{tid} done"

    @reg.register("reminder_add", "set a reminder for a time (remind me later)", {"text": "what to remind", "when": "in 30 minutes | tomorrow 9:00 | YYYY-MM-DD HH:MM"}, feature="reminders")
    def reminder_add(text: str, when: str) -> str:
        due = parse_when(when)
        rid = store.x("INSERT INTO reminders(text,due,created) VALUES(?,?,?)", (str(text)[:300], due, time.time()))
        return f"reminder #{rid} set for {fmt_ts(due)}: {text}"

    @reg.register("reminder_list", "list pending reminders", {}, feature="reminders")
    def reminder_list() -> str:
        rows = store.q("SELECT id,text,due FROM reminders WHERE fired=0 ORDER BY due")
        return "; ".join(f"#{r['id']} {r['text']} at {fmt_ts(r['due'])}" for r in rows) or "no pending reminders"

    @reg.register("daily_brief", "summary of today: todos, reminders, notes and activity (morning brief)", {}, feature="daily_brief")
    def daily_brief() -> str:
        return brief_text(store)

    @reg.register("journal_add", "add a private journal entry", {"text": "entry", "mood": "optional mood word"}, feature="journal", optional=("mood",))
    def journal_add(text: str, mood: str = "") -> str:
        store.x("INSERT INTO journal(text,mood,created) VALUES(?,?,?)", (str(text)[:2000], str(mood)[:20], time.time()))
        store.add_fact("journal", str(text))
        return "journal entry saved"

    @reg.register("journal_search", "search past journal entries", {"query": "search text"}, feature="journal")
    def journal_search(query: str) -> str:
        hits = store.search_facts(str(query), k=3, kinds=("journal",), min_sim=0.07)
        return " | ".join(h["text"][:160] for h in hits) or "no matching entries"

    @reg.register("calendar_upcoming", "upcoming events from .ics calendar files in the workspace (schedule, agenda)", {"days": "look-ahead days"}, feature="calendar", optional=("days",))
    def calendar_upcoming(days: str = "7") -> str:
        now = time.time()
        end = now + int(days) * 86400
        evs = []
        for p in ctx.text_files(".", {".ics"}):
            evs += ics_events(read_text(p))
        evs = sorted(e for e in evs if now <= e[0] <= end)
        return "; ".join(f"{fmt_ts(t)} {s}" for t, s in evs[:15]) or f"no events in the next {days} days (recurring events are not expanded)"
