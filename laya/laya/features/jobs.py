"""Background jobs run by the scheduler thread. Each takes the Laya object and returns a status message."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..core import Laya


def reminders(laya: "Laya") -> str:
    now = time.time()
    due = laya.store.q("SELECT id,text FROM reminders WHERE fired=0 AND due<=?", (now,))
    for r in due:
        laya.store.x("UPDATE reminders SET fired=1 WHERE id=?", (r["id"],))
        laya.store.add_fact("reminder", f"REMINDER: {r['text']}", score=2.0)
        laya.store.x("INSERT INTO notes(text,created) VALUES(?,?)", (f"⏰ Reminder: {r['text']}", now))
    return f"fired {len(due)} reminder(s)"


def watch_folder(laya: "Laya") -> str:
    from ..tools.helpers import Ctx
    from ..tools.kb import ingest

    r = ingest(Ctx(laya.settings, laya.store, laya.registry, laya.settings.workspace.resolve()))
    return f"{r['new_files']} new, {r['updated_files']} updated files ({r['chunks']} chunks)"


def auto_brief(laya: "Laya") -> str:
    from ..tools.assistant import brief_text

    today = time.strftime("%Y-%m-%d")
    if laya.store.get_kv("last_brief_date") == today:
        return "already generated today"
    laya.store.set_kv("last_brief_date", today)
    laya.store.add_fact("brief", f"{today}: {brief_text(laya.store)}", score=1.0)
    return "brief generated"


def self_practice(laya: "Laya") -> str:
    from ..learning.curriculum import practice

    r = practice(laya, 3)
    return f"{r['passed']}/{r['tasks']} correct, {r['new_skills']} new skills"


JOBS: dict[str, Callable[["Laya"], str]] = {
    "reminders": reminders, "watch_folder": watch_folder, "auto_brief": auto_brief, "self_practice": self_practice,
}
