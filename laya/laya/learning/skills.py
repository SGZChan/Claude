"""Skill library: successful tool traces become reusable, parameterised macros.

A goal is reduced to a *shape* (numbers and quoted strings replaced by slots). When
the same shape produces the same templated tool sequence `promote_after` times, it is
promoted to a skill. The System-One router then runs it directly, with no LLM call.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from ..memory.store import Store

# numbers may be negative ("-4") unless the minus is a subtraction sign ("5-3")
TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|(?<![\w.)])-?\d+(?:\.\d+)?")
PLACEHOLDER = re.compile(r"⟦([sr])(\d+)⟧")


def shape_and_slots(goal: str) -> tuple[str, list[str]]:
    slots: list[str] = []

    def sub(m: re.Match) -> str:
        t = m.group(0)
        if t[0] in "\"'":
            slots.append(t[1:-1])
            return "<s>"
        slots.append(t)
        return "<n>"

    shape = TOKEN.sub(sub, goal.strip().lower())
    return re.sub(r"\s+", " ", shape).strip(" .!?"), slots


def _literal_re(lit: str) -> str:
    return r"(?<![\w.])" + re.escape(lit) + r"(?![\w])"


def template_steps(steps: list[dict[str, Any]], slots: list[str]) -> list[dict[str, Any]]:
    out = []
    results: list[str] = []
    for st in steps:
        args = {}
        cands: dict[str, str] = {}
        for i, r in enumerate(results):  # earlier results first, slots override on ties
            if r:
                cands[r] = f"⟦r{i}⟧"
        for i, s in enumerate(slots):
            if s:
                cands[s] = f"⟦s{i}⟧"
        for k, v in st["args"].items():
            if isinstance(v, str) and cands:
                pat = "|".join(_literal_re(c) for c in sorted(cands, key=len, reverse=True))
                v = re.sub(pat, lambda m: cands[m.group(0)], v)
            args[k] = v
        out.append({"tool": st["tool"], "args": args})
        results.append(str(st.get("result", "")).strip())
    return out


def render_args(args: dict[str, Any], slots: list[str], results: list[str]) -> dict[str, Any]:
    def sub(m: re.Match) -> str:
        src = slots if m.group(1) == "s" else results
        return src[int(m.group(2))]

    return {k: PLACEHOLDER.sub(sub, v) if isinstance(v, str) else v for k, v in args.items()}


class SkillLibrary:
    def __init__(self, store: Store, promote_after: int = 3) -> None:
        self.store = store
        self.promote_after = promote_after

    def record_success(self, goal: str, steps: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Register a successful agent trace. Returns the skill row if this promoted one."""
        if not steps or not all(s.get("ok") for s in steps):
            return None
        shape, slots = shape_and_slots(goal)
        tsteps = template_steps(steps, slots)
        key = hashlib.sha1((shape + json.dumps(tsteps, sort_keys=True)).encode()).hexdigest()
        now = time.time()
        self.store.x("INSERT INTO candidates(key,shape,steps,count,updated) VALUES(?,?,?,1,?) "
                     "ON CONFLICT(key) DO UPDATE SET count=count+1, updated=excluded.updated",
                     (key, shape, json.dumps(tsteps), now))
        count = self.store.q("SELECT count FROM candidates WHERE key=?", (key,))[0]["count"]
        if count >= self.promote_after and not self.store.q("SELECT id FROM skills WHERE shape=?", (shape,)):
            sid = self.store.x("INSERT INTO skills(name,shape,steps,successes,created) VALUES(?,?,?,?,?)",
                               (shape[:48], shape, json.dumps(tsteps), count, now))
            return self.get(sid)
        return None

    def retract(self, goal: str, steps: list[dict[str, Any]]) -> None:
        """A user 👎 on an agent run removes its vote toward promotion."""
        shape, slots = shape_and_slots(goal)
        key = hashlib.sha1((shape + json.dumps(template_steps(steps, slots), sort_keys=True)).encode()).hexdigest()
        self.store.x("UPDATE candidates SET count=MAX(count-1,0) WHERE key=?", (key,))

    def get(self, sid: int) -> dict[str, Any] | None:
        r = self.store.q("SELECT * FROM skills WHERE id=?", (sid,))
        if not r:
            return None
        r[0]["steps"] = json.loads(r[0]["steps"])
        return r[0]

    def list(self) -> list[dict[str, Any]]:
        rows = self.store.q("SELECT * FROM skills ORDER BY id DESC")
        for r in rows:
            r["steps"] = json.loads(r["steps"])
        return rows

    def match(self, goal: str) -> tuple[dict[str, Any], list[str]] | None:
        shape, slots = shape_and_slots(goal)
        r = self.store.q("SELECT id FROM skills WHERE shape=? AND enabled=1", (shape,))
        if not r:
            return None
        return self.get(r[0]["id"]), slots  # type: ignore[return-value]

    def record_use(self, sid: int, ok: bool) -> None:
        self.store.x("UPDATE skills SET uses=uses+1, successes=successes+?, failures=failures+?, last_used=? WHERE id=?",
                     (1 if ok else 0, 0 if ok else 1, time.time(), sid))
        self._rescore(sid)

    def rate(self, sid: int, rating: int) -> None:
        """rating +1/-1 from the user; nudges score and may auto-disable bad skills."""
        self.store.x("UPDATE skills SET score=MAX(0, MIN(1, score + ?)) WHERE id=?", (0.1 if rating > 0 else -0.5, sid))
        self._rescore(sid)

    def _rescore(self, sid: int) -> None:
        s = self.get(sid)
        if s and s["score"] < 0.3 or (s and s["uses"] >= 3 and s["failures"] / max(s["uses"], 1) > 0.5):
            self.store.x("UPDATE skills SET enabled=0 WHERE id=?", (sid,))

    def set_enabled(self, sid: int, enabled: bool) -> None:
        self.store.x("UPDATE skills SET enabled=?, score=CASE WHEN ?=1 AND score<0.5 THEN 0.5 ELSE score END WHERE id=?",
                     (1 if enabled else 0, 1 if enabled else 0, sid))

    def delete(self, sid: int) -> None:
        self.store.x("DELETE FROM skills WHERE id=?", (sid,))
