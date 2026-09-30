from __future__ import annotations

from typing import Any

from ..llm.base import LLM
from ..memory.store import Store


def reflect(llm: LLM, store: Store, goal: str, steps: list[dict[str, Any]], ok: bool) -> str:
    trace = "; ".join(f"{s['tool']}({s['args']}) -> {'ok' if s.get('ok') else 'error'}" for s in steps) or "no tools used"
    prompt = (
        "Write ONE short lesson (max 20 words) that would help solve similar goals next time.\n"
        f"GOAL: {goal}\nOUTCOME: {'success' if ok else 'failure'}\nTRACE: {trace}\nLesson:"
    )
    lines = llm.generate(prompt, task="reflect", max_tokens=48).strip().splitlines()
    lesson = lines[0][:200] if lines else ""
    if lesson:
        store.add_fact("lesson", f"{goal[:60]} => {lesson}", score=1.0 if ok else 0.6)
    return lesson
