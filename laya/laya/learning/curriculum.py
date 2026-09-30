"""Self-practice: run tasks whose answers can be verified, so Laya can learn skills while idle.

Tasks come from a built-in arithmetic generator plus any custom tasks the user added (Learning page)."""
from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING, Any, Callable

from . import tasks as T

if TYPE_CHECKING:
    from ..core import Laya

Instance = tuple[str, Callable[[dict[str, Any]], tuple[bool, str]], "int | None"]  # goal, check(res) -> (ok, why), task id


def _builtin(rng: random.Random) -> Instance:
    a, b = rng.randint(2, 99), rng.randint(2, 99)
    op = rng.choice(["+", "-", "*"])
    want = {"+": a + b, "-": a - b, "*": a * b}[op]
    return (f"What is {a}{op}{b}?",
            lambda res, w=want: (res["status"] == "ok" and res["answer"].strip() == str(w), f"expected {w}"), None)


def _custom(task: dict[str, Any], rng: random.Random) -> Instance:
    values = T.draw(T.parse_params(task["params"]), rng)
    goal = T.fill(task["template"], values)
    return goal, (lambda res: T.check(task, values, res["answer"], res["steps"], res["status"])), task["id"]


def practice(laya: "Laya", n: int = 6, seed: int | None = None, task_id: int | None = None) -> dict:
    """Run n practice goals. task_id limits it to one custom task; otherwise built-in + all enabled custom tasks are mixed."""
    rng = random.Random(seed)
    custom = []
    if laya.features.enabled("custom_practice"):
        custom = [t for t in T.list_tasks(laya.store, only_enabled=task_id is None) if task_id in (None, t["id"])]
    if task_id is not None and not custom:
        raise T.TaskError("no such task (or the Custom practice tasks feature is off)")
    pool: list[dict[str, Any] | None] = [None, *custom] if task_id is None else list(custom)
    passed = via_skill = 0
    skills_before = len(laya.skills.list())
    by_task: dict[str, dict[str, int]] = {}
    failures: list[dict[str, str]] = []
    for _ in range(n):
        t = pool[0] if len(pool) == 1 else rng.choice(pool)  # no extra rng draw when there's only one source
        goal, check, tid = _builtin(rng) if t is None else _custom(t, rng)
        res = laya.agent.run(goal, source="practice")
        ok, why = check(res)
        passed += int(ok)
        via_skill += int(res["via"] == "skill")
        name = "Built-in arithmetic" if t is None else t["name"]
        s = by_task.setdefault(name, {"runs": 0, "passed": 0})
        s["runs"] += 1
        s["passed"] += int(ok)
        if not ok:
            detail = f"{goal} -> {res['answer'] or res['error'] or '(no answer)'} ({why})"
            failures.append({"task": name, "detail": detail})
        if tid is not None:
            T.record_result(laya.store, tid, ok, "" if ok else detail)
    result = {"tasks": n, "passed": passed, "via_skill": via_skill, "new_skills": len(laya.skills.list()) - skills_before,
              "by_task": by_task, "failures": failures[:5]}
    laya.store.set_kv("last_practice", json.dumps(result))
    return result
