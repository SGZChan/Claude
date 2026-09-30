"""Self-practice: run synthetic tasks whose answers can be verified by computation."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..core import Laya


def _tasks(rng: random.Random, n: int) -> list[tuple[str, Callable[[str], bool]]]:
    out = []
    for _ in range(n):
        a, b = rng.randint(2, 99), rng.randint(2, 99)
        op = rng.choice(["+", "-", "*"])
        want = {"+": a + b, "-": a - b, "*": a * b}[op]
        out.append((f"What is {a}{op}{b}?", lambda ans, w=want: ans.strip() == str(w)))
    return out


def practice(laya: "Laya", n: int = 6, seed: int | None = None) -> dict:
    rng = random.Random(seed)
    passed = via_skill = 0
    skills_before = len(laya.skills.list())
    for goal, check in _tasks(rng, n):
        res = laya.agent.run(goal, source="practice")
        passed += int(res["status"] == "ok" and check(res["answer"]))
        via_skill += int(res["via"] == "skill")
    result = {"tasks": n, "passed": passed, "via_skill": via_skill,
              "new_skills": len(laya.skills.list()) - skills_before}
    laya.store.set_kv("last_practice", __import__("json").dumps(result))
    return result
