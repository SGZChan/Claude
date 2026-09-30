"""Deterministic rule-based stand-in for a small LLM.

Used for tests, CI and offline demos. It reads the same prompt a real model would
and answers in the same JSON protocol, so the whole agent stack is exercised.
"""
from __future__ import annotations

import json
import re
from typing import Any

_MATH = re.compile(r"(\d[\d\s+\-*/().%]*\d|\d)")


def _find_expr(goal: str) -> str | None:
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
