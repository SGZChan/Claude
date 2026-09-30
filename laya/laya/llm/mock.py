"""Deterministic rule-based stand-in for a small LLM.

Used for tests, CI and offline demos. It reads the same prompt a real model would
and answers in the same JSON protocol, so the whole agent stack is exercised.
"""
from __future__ import annotations

import json
import re
from typing import Any

_MATH = re.compile(r"(\d[\d\s+\-*/().%]*\d|\d)")
_NOISE = re.compile(r"https?://\S+|\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|#\d+|\S+\.\w{2,4}\b")
_WHEN = r"(in \d+ \w+|tomorrow(?: \d{1,2}(?::\d{2})?)?|today \d{1,2}(?::\d{2})?)"
I = re.I

# (pattern, builder) - checked before the generic arithmetic / note logic. Mimics a model that picks the right tool.
RULES = [
    (re.compile(r"\bremind me to\s+(.+?)\s+" + _WHEN + r"\s*$", I), lambda m: ("reminder_add", {"text": m[1], "when": m[2]})),
    (re.compile(r"\b(?:add (?:a )?todo|todo:)\s*(.+)$", I), lambda m: ("todo_add", {"text": m[1].strip()})),
    (re.compile(r"\b(?:finish|complete|done with) todo #?(\d+)", I), lambda m: ("todo_done", {"id": m[1]})),
    (re.compile(r"\b(?:list|show|my)\b.*\b(?:todos?|tasks)\b", I), lambda m: ("todo_list", {})),
    (re.compile(r"\b(?:daily|morning) brief|brief me", I), lambda m: ("daily_brief", {})),
    (re.compile(r"\bsearch (?:my )?journal (?:for )?(.+)$", I), lambda m: ("journal_search", {"query": m[1]})),
    (re.compile(r"\bjournal:?\s+(.+)$", I), lambda m: ("journal_add", {"text": m[1]})),
    (re.compile(r"upcoming events|my calendar|agenda", I), lambda m: ("calendar_upcoming", {})),
    (re.compile(r"\bconvert\s+(-?[\d.]+)\s*(\w+)\s+to\s+(\w+)", I), lambda m: ("unit_convert", {"value": m[1], "from_unit": m[2], "to_unit": m[3]})),
    (re.compile(r"days between (\d{4}-\d{2}-\d{2}) and (\d{4}-\d{2}-\d{2})", I), lambda m: ("date_diff", {"a": m[1], "b": m[2]})),
    (re.compile(r"(-?\d+) days (?:from|after) (\d{4}-\d{2}-\d{2}|today)", I), lambda m: ("date_math", {"start": m[2], "days": m[1]})),
    (re.compile(r"passphrase", I), lambda m: ("passphrase", {})),
    (re.compile(r"\bpassword\b", I), lambda m: ("password_gen", {})),
    (re.compile(r"\btext stats?:\s*(.+)$", I), lambda m: ("text_stats", {"text": m[1]})),
    (re.compile(r"\btriage inbox (\S+)", I), lambda m: ("triage_inbox", {"path": m[1]})),
    (re.compile(r"\btriage(?: this)?:\s*(.+)$", I), lambda m: ("triage_text", {"text": m[1]})),
    (re.compile(r"\bdraft (?:a )?reply(?: to)?:\s*(.+)$", I), lambda m: ("draft_reply", {"text": m[1]})),
    (re.compile(r"\bcsv stats (\S+\.csv) (\w+)", I), lambda m: ("csv_stats", {"path": m[1], "column": m[2]})),
    (re.compile(r"\bcsv head (\S+\.csv)", I), lambda m: ("csv_head", {"path": m[1]})),
    (re.compile(r"\bgroup (\S+\.csv) by (\w+)", I), lambda m: ("csv_group", {"path": m[1], "column": m[2]})),
    (re.compile(r"\b(?:ingest|index) (?:my )?(?:documents|knowledge base|files)", I), lambda m: ("kb_ingest", {})),
    (re.compile(r"(?:ask my knowledge base|\bkb:|what do my documents say)\s*(?:about )?(.+)$", I), lambda m: ("kb_ask", {"question": m[1]})),
    (re.compile(r"\bsummari[sz]e (\S+\.\w+)", I), lambda m: ("file_summarize", {"path": m[1]})),
    (re.compile(r"\bsearch files for (.+)$", I), lambda m: ("file_search", {"query": m[1]})),
    (re.compile(r"\bextract (emails|urls|numbers|dates) from (\S+)", I), lambda m: ("file_extract", {"path": m[2], "kind": m[1]})),
    (re.compile(r"\bgit status", I), lambda m: ("git_status", {})),
    (re.compile(r"\bgit log", I), lambda m: ("git_log", {})),
    (re.compile(r"\bgit diff", I), lambda m: ("git_diff", {})),
    (re.compile(r"\b(?:find code|search code for)\s+(.+)$", I), lambda m: ("repo_search", {"pattern": m[1]})),
    (re.compile(r"\bdigest (https://\S+)", I), lambda m: ("web_digest", {"url": m[1]})),
    (re.compile(r"\brun python:\s*(.+)$", I), lambda m: ("python_sandbox", {"code": m[1]})),
]


def _find_expr(goal: str) -> str | None:
    goal = _NOISE.sub(" ", goal)
    for m in _MATH.finditer(goal):
        s = m.group(1).strip()
        if re.search(r"[+\-*/%]", s) and re.search(r"\d", s):
            return s
    return None


class MockLLM:
    name = "mock"

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None, task: str = "act", max_tokens: int = 256) -> str:
        if task == "reflect":
            m = re.search(r"GOAL: (.*)", prompt)
            ok = "OUTCOME: success" in prompt
            goal = (m.group(1) if m else "task")[:80]
            return f"{'Worked' if ok else 'Failed'} for '{goal}'; reuse the same tool order." if ok else f"Avoid repeating the failing step for '{goal}'."
        goal_m = re.search(r"GOAL: (.*)", prompt)
        goal = goal_m.group(1).strip() if goal_m else ""
        used = re.findall(r"^STEP \d+: (\w+)\(", prompt, re.M)
        obs = re.findall(r"^-> (.*)$", prompt, re.M)
        last = obs[-1] if obs else ""
        low = goal.lower()
        wants_note = bool(re.search(r"\b(save|note|remember)\b", low))
        expr = _find_expr(goal)

        for rx, build in RULES:
            if m := rx.search(goal):
                tool, args = build(m)
                if tool not in used:
                    return json.dumps({"tool": tool, "args": args})
        if expr and "calculator" not in used:
            return json.dumps({"tool": "calculator", "args": {"expression": expr}})
        if wants_note and "notes_add" not in used:
            text = f"{expr} = {last}" if expr and last else (re.sub(r"^(please )?(note|remember|save)( that)?:?\s*", "", goal, flags=re.I) or goal)
            return json.dumps({"tool": "notes_add", "args": {"text": text}})
        if re.search(r"\blist (the )?files\b", low) and "file_list" not in used:
            return json.dumps({"tool": "file_list", "args": {"path": "."}})
        m = re.search(r"\bread (?:file )?([\w./-]+\.\w+)", low)
        if m and "file_read" not in used:
            return json.dumps({"tool": "file_read", "args": {"path": m.group(1)}})
        if re.search(r"\b(time|date)\b", low) and "get_time" not in used:
            return json.dumps({"tool": "get_time", "args": {}})
        if re.search(r"\b(show|list) (my )?notes\b", low) and "notes_list" not in used:
            return json.dumps({"tool": "notes_list", "args": {}})
        return json.dumps({"final": last or "I don't know how to do that yet."})

    def info(self) -> dict[str, Any]:
        return {"backend": self.name, "model": "scripted-mock", "tokens_per_sec": 0.0}
