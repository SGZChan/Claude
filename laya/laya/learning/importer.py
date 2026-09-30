"""Import a training-data JSONL file (as produced by Learning -> Download training data).

One JSON object per line:  {"prompt": "What is 2*3?", "actions": [{"tool": "calculator", "args": {...}, "result": "6"}], "final": "6"}

Each valid trace is a successful example. It counts as one vote toward promoting a skill (same rules as a real run:
`promote_after` distinct agreeing examples create one) and can also be stored as a short lesson. Nothing is executed.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core import Laya

MAX_LINES, MAX_ACTIONS, MAX_PROMPT, MAX_ARG = 5000, 8, 500, 2000
SCALARS = (str, int, float, bool, type(None))


class ImportErr(ValueError):
    pass


def parse_line(obj: Any, known_tools: set[str]) -> tuple[str, list[dict[str, Any]], bool]:
    """Validate one record. Returns (prompt, steps, has_results); raises ImportErr with a reason."""
    if not isinstance(obj, dict):
        raise ImportErr("not a JSON object")
    prompt = obj.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImportErr("missing 'prompt'")
    if len(prompt) > MAX_PROMPT:
        raise ImportErr(f"prompt longer than {MAX_PROMPT} characters")
    actions = obj.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ImportErr("'actions' must be a non-empty list")
    if len(actions) > MAX_ACTIONS:
        raise ImportErr(f"more than {MAX_ACTIONS} actions")
    steps, has_results = [], True
    for i, a in enumerate(actions, 1):
        if not isinstance(a, dict) or not isinstance(a.get("tool"), str) or not isinstance(a.get("args", {}), dict):
            raise ImportErr(f"action {i} must look like {{\"tool\": \"name\", \"args\": {{...}}}}")
        if a["tool"] not in known_tools:
            raise ImportErr(f"action {i}: unknown tool '{a['tool']}'")
        args = a.get("args", {})
        for k, v in args.items():
            if not isinstance(v, SCALARS) or (isinstance(v, str) and len(v) > MAX_ARG):
                raise ImportErr(f"action {i}: argument '{k}' must be a short string or number")
        if "result" not in a:
            has_results = False
        steps.append({"tool": a["tool"], "args": args, "result": str(a.get("result", "")), "ok": True})
    return prompt.strip(), steps, has_results


def import_jsonl(laya: "Laya", text: str, learn_skills: bool = True, add_lessons: bool = True, dry_run: bool = False) -> dict[str, Any]:
    store, known = laya.store, set(laya.registry.tools)
    out: dict[str, Any] = {"lines": 0, "valid": 0, "duplicates": 0, "votes": 0, "lessons": 0, "skills_promoted": [],
                           "invalid": [], "skipped": [], "dry_run": dry_run}
    raw = text.lstrip("﻿").splitlines()
    if len([ln for ln in raw if ln.strip()]) > MAX_LINES:
        raise ImportErr(f"too many lines (max {MAX_LINES})")
    for n, line in enumerate(raw, 1):
        if not line.strip():
            continue
        out["lines"] += 1
        try:
            prompt, steps, has_results = parse_line(json.loads(line), known)
        except json.JSONDecodeError:
            out["invalid"].append({"line": n, "error": "not valid JSON"})
            continue
        except ImportErr as e:
            out["invalid"].append({"line": n, "error": str(e)})
            continue
        # A later step's arguments may be built from earlier results; without results we can't template
        # them safely, so multi-step traces from older exports are skipped rather than learned wrongly.
        if len(steps) > 1 and not has_results:
            out["skipped"].append({"line": n, "reason": "multi-step trace without recorded results (re-export from a newer Laya)"})
            continue
        out["valid"] += 1
        h = hashlib.sha1(json.dumps([prompt, [(s["tool"], s["args"], s["result"]) for s in steps]], sort_keys=True).encode()).hexdigest()
        if store.q("SELECT 1 FROM imported_traces WHERE hash=?", (h,)):
            out["duplicates"] += 1
            continue
        if dry_run:
            continue
        store.x("INSERT INTO imported_traces(hash,created) VALUES(?,?)", (h, time.time()))
        if learn_skills:
            promoted = laya.skills.record_success(prompt, steps)
            out["votes"] += 1
            if promoted:
                out["skills_promoted"].append(promoted["name"])
                store.add_fact("lesson", f"Learned skill '{promoted['name']}' (imported)", score=1.0)
        if add_lessons:
            store.add_fact("lesson", f"{prompt[:60]} => worked with " + " then ".join(s["tool"] for s in steps), score=1.0)
            out["lessons"] += 1
    out["invalid"], out["skipped"] = out["invalid"][:10], out["skipped"][:10]
    return out
