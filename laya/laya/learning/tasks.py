"""User-defined practice tasks.

A task is a goal *template* with random *parameters* and a *check* that decides whether Laya's answer was right:

    template:  Convert {a} miles to km
    params:    a: int 1..50
    check:     expr  {a}*1.609344      (numeric, relative tolerance)

Check types: succeeds | equals | contains | regex | expr | tool.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import time
from typing import Any

from ..memory.store import Store
from ..tools.builtin import safe_eval
from ..tools.registry import ToolError

CHECK_TYPES = ("succeeds", "equals", "contains", "regex", "expr", "tool")
MAX_TASKS = 200
PLACEHOLDER = re.compile(r"\{(\w+)\}")
INT_RE = re.compile(r"^(\w+)\s*:\s*(int|float)\s+(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)$", re.I)
CHOICE_RE = re.compile(r"^(\w+)\s*:\s*choice\s+(.+)$", re.I)


class TaskError(ValueError):
    pass


def parse_params(text: str) -> dict[str, dict[str, Any]]:
    """One parameter per line (or separated by ';'):  a: int 2..99 | x: float 0.5..9.5 | op: choice + | - | *  (or 'choice +, -, *')"""
    out: dict[str, dict[str, Any]] = {}
    for line in re.split(r"[\n;]", text or ""):
        line = line.strip()
        if not line:
            continue
        if m := INT_RE.match(line):
            name, kind, lo, hi = m[1], m[2].lower(), float(m[3]), float(m[4])
            if lo > hi:
                raise TaskError(f"parameter '{name}': min is greater than max")
            out[name] = {"type": kind, "min": lo, "max": hi}
        elif m := CHOICE_RE.match(line):
            sep = "|" if "|" in m[2] else ","  # 'choice a | b' or 'choice a, b'
            vals = [v.strip() for v in m[2].split(sep) if v.strip()]
            if not vals:
                raise TaskError(f"parameter '{m[1]}': give at least one choice, separated by |")
            out[m[1]] = {"type": "choice", "values": vals}
        else:
            raise TaskError(f"can't read parameter line '{line}'. Use 'a: int 1..50', 'x: float 0.5..9.5' or 'op: choice + | - | *'")
    return out


def fill(template: str, values: dict[str, Any]) -> str:
    return PLACEHOLDER.sub(lambda m: str(values.get(m[1], m[0])), template)


def draw(params: dict[str, dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    for name, p in params.items():  # dict order is stable, so a seed reproduces the same task
        if p["type"] == "int":
            vals[name] = rng.randint(int(p["min"]), int(p["max"]))
        elif p["type"] == "float":
            vals[name] = round(rng.uniform(p["min"], p["max"]), 2)
        else:
            vals[name] = rng.choice(p["values"])
    return vals


def validate(d: dict[str, Any]) -> dict[str, Any]:
    """Normalise and validate a task definition; raises TaskError with a human-readable message."""
    name, template = str(d.get("name", "")).strip(), str(d.get("template", "")).strip()
    ctype, cval = str(d.get("check_type", "succeeds")).strip().lower(), str(d.get("check_value", "")).strip()
    if not name or len(name) > 80:
        raise TaskError("name is required (max 80 characters)")
    if not template or len(template) > 300:
        raise TaskError("goal template is required (max 300 characters)")
    if ctype not in CHECK_TYPES:
        raise TaskError(f"check type must be one of: {', '.join(CHECK_TYPES)}")
    if ctype != "succeeds" and not cval:
        raise TaskError(f"check type '{ctype}' needs a check value")
    try:
        tol = float(d.get("tolerance", 0.001))
    except (TypeError, ValueError):
        raise TaskError("tolerance must be a number")
    if not 0 <= tol <= 1:
        raise TaskError("tolerance must be between 0 and 1")
    params_text = str(d.get("params", "") or "").strip()
    params = parse_params(params_text)
    unknown = (set(PLACEHOLDER.findall(template)) | set(PLACEHOLDER.findall(cval))) - set(params)
    if unknown:
        raise TaskError(f"undefined placeholder(s): {', '.join('{' + u + '}' for u in sorted(unknown))}. Define them under Parameters")
    if ctype == "regex":
        try:
            re.compile(fill(cval, {k: "1" for k in params}))
        except re.error as e:
            raise TaskError(f"bad regular expression: {e}")
    if ctype == "expr":
        try:
            safe_eval(fill(cval, draw(params, random.Random(0))))
        except ToolError as e:
            raise TaskError(f"expression can't be evaluated ({e}); use numbers, + - * / ** % and parameters")
    return {"name": name, "template": template, "params": params_text, "check_type": ctype, "check_value": cval,
            "tolerance": tol, "enabled": 1 if d.get("enabled", True) else 0}


def check(task: dict[str, Any], values: dict[str, Any], answer: str, steps: list[dict[str, Any]], status: str) -> tuple[bool, str]:
    """Did Laya do this task correctly? Returns (passed, reason)."""
    if status != "ok":
        return False, f"run {status}"
    t, v = task["check_type"], fill(task["check_value"], values)
    ans = (answer or "").strip()
    if t == "succeeds":
        return True, ""
    if t == "equals":
        return (ans.lower() == v.lower()), f"expected exactly '{v}'"
    if t == "contains":
        return (v.lower() in ans.lower()), f"expected the answer to contain '{v}'"
    if t == "regex":
        return bool(re.search(v, ans, re.I)), f"expected the answer to match /{v}/"
    if t == "tool":
        return any(s["tool"] == v and s.get("ok") for s in steps), f"expected tool '{v}' to run successfully"
    if t == "expr":
        try:
            want = float(safe_eval(v))
        except ToolError as e:
            return False, f"bad expression: {e}"
        tol = float(task.get("tolerance") or 0.001)
        for n in re.findall(r"-?\d+(?:\.\d+)?", ans.replace(",", "")):
            if abs(float(n) - want) <= tol * max(1.0, abs(want)):
                return True, ""
        return False, f"expected about {want:g}"
    return False, "unknown check"


# ---------------------------------------------------------------- persistence
COLS = ("name", "template", "params", "check_type", "check_value", "tolerance", "enabled")


def list_tasks(store: Store, only_enabled: bool = False) -> list[dict[str, Any]]:
    rows = store.q("SELECT * FROM practice_tasks" + (" WHERE enabled=1" if only_enabled else "") + " ORDER BY id")
    for r in rows:
        r["pass_rate"] = round(r["passes"] / r["runs"], 3) if r["runs"] else None
    return rows


def add_task(store: Store, d: dict[str, Any]) -> int:
    v = validate(d)
    if len(list_tasks(store)) >= MAX_TASKS:
        raise TaskError(f"limit of {MAX_TASKS} tasks reached")
    if store.q("SELECT id FROM practice_tasks WHERE name=?", (v["name"],)):
        raise TaskError(f"a task named '{v['name']}' already exists")
    return store.x(f"INSERT INTO practice_tasks({','.join(COLS)},created) VALUES({','.join('?' * len(COLS))},?)",
                   (*[v[c] for c in COLS], time.time()))


def update_task(store: Store, tid: int, d: dict[str, Any]) -> None:
    v = validate(d)
    if not store.q("SELECT id FROM practice_tasks WHERE id=?", (tid,)):
        raise TaskError("no such task")
    if store.q("SELECT id FROM practice_tasks WHERE name=? AND id!=?", (v["name"], tid)):
        raise TaskError(f"a task named '{v['name']}' already exists")
    store.x(f"UPDATE practice_tasks SET {','.join(c + '=?' for c in COLS)}, runs=0, passes=0, last_fail='' WHERE id=?",
            (*[v[c] for c in COLS], tid))


def record_result(store: Store, tid: int, ok: bool, detail: str) -> None:
    store.x("UPDATE practice_tasks SET runs=runs+1, passes=passes+?, last_fail=CASE WHEN ?=1 THEN last_fail ELSE ? END WHERE id=?",
            (1 if ok else 0, 1 if ok else 0, detail[:300], tid))


STARTER_PACK: list[dict[str, Any]] = [
    {"name": "Miles to km", "template": "Convert {a} miles to km", "params": "a: int 1..50", "check_type": "expr", "check_value": "{a}*1.609344", "tolerance": 0.001},
    {"name": "Celsius to Fahrenheit", "template": "Convert {c} c to f", "params": "c: int -20..40", "check_type": "expr", "check_value": "{c}*9/5+32", "tolerance": 0.001},
    {"name": "Mixed arithmetic", "template": "What is {a}{op}{b}?", "params": "a: int 2..60\nb: int 2..60\nop: choice + | - | *", "check_type": "expr", "check_value": "{a}{op}{b}", "tolerance": 0},
    {"name": "Days between dates", "template": "How many days between 2026-01-{d1} and 2026-03-{d2}", "params": "d1: int 10..28\nd2: int 10..28", "check_type": "tool", "check_value": "date_diff"},
    {"name": "Passphrase", "template": "Generate a passphrase", "check_type": "tool", "check_value": "passphrase"},
    {"name": "Text statistics", "template": "Text stats: {w1} {w2} {w3}", "params": "w1: choice red | green | blue\nw2: choice cat | dog | fox\nw3: choice runs | jumps | sleeps", "check_type": "contains", "check_value": "3 words"},
]


def add_starter_pack(store: Store) -> int:
    added = 0
    for d in STARTER_PACK:
        try:
            add_task(store, d)
            added += 1
        except TaskError:
            pass  # already there
    return added


def export_tasks(store: Store) -> list[dict[str, Any]]:
    return [{c: t[c] for c in COLS if c != "enabled"} | {"enabled": bool(t["enabled"])} for t in list_tasks(store)]


def import_tasks(store: Store, items: list[Any]) -> dict[str, Any]:
    added, errors = 0, []
    for i, d in enumerate(items[:MAX_TASKS]):
        try:
            if not isinstance(d, dict):
                raise TaskError("each task must be an object")
            add_task(store, d)
            added += 1
        except TaskError as e:
            errors.append(f"#{i + 1} {d.get('name', '') if isinstance(d, dict) else ''}: {e}".strip())
    return {"added": added, "errors": errors}


# ---------------------------------------------------------------- batch adding
BATCH_FIELDS = ("name", "template", "params", "check_type", "check_value", "tolerance")


def parse_batch(text: str) -> tuple[str, list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    """Turn pasted/uploaded text into task dicts. Formats (auto-detected):

    * JSON array of task objects                       [{"name": ...}, ...]
    * JSONL, one task object per line                  {"name": ...}
    * CSV with a header row                            name,template,params,check_type,check_value,tolerance
    * simple lines, fields separated by |              name | template | params | check_type | check_value | tolerance
      (only name and template are required; blank lines and lines starting with # are ignored;
       in the params column separate parameters with ';' and choices with ',')

    Returns (format, [(line_no, task_dict)], [{"line", "error"}])."""
    t = text.lstrip("\ufeff").strip()
    if not t:
        raise TaskError("nothing to add: paste some tasks or choose a file")
    items: list[tuple[int, dict[str, Any]]] = []
    errors: list[dict[str, Any]] = []
    first = t.splitlines()[0].strip().lower()
    if t[0] == "[":
        try:
            arr = json.loads(t)
        except json.JSONDecodeError as e:
            raise TaskError(f"invalid JSON: {e.msg} (line {e.lineno})")
        fmt = "json"
        for i, d in enumerate(arr, 1):
            (items.append((i, d)) if isinstance(d, dict) else errors.append({"line": i, "error": "each task must be an object"}))
    elif t[0] == "{":
        fmt = "jsonl"
        for n, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                (items.append((n, d)) if isinstance(d, dict) else errors.append({"line": n, "error": "each task must be an object"}))
            except json.JSONDecodeError:
                errors.append({"line": n, "error": "not valid JSON"})
    elif first.startswith("name,") or first.startswith("name\t"):
        fmt = "csv"
        dialect = csv.excel_tab if first.startswith("name\t") else csv.excel
        for i, row in enumerate(csv.DictReader(io.StringIO(t), dialect=dialect), 2):
            items.append((i, {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}))
    else:
        fmt = "lines"
        for n, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
            if not line.strip() or line.strip().startswith("#"):
                continue
            f = [x.strip() for x in line.split("|")]
            if len(f) < 2:
                errors.append({"line": n, "error": "need at least: name | goal template"})
            elif len(f) > len(BATCH_FIELDS):
                errors.append({"line": n, "error": "too many '|' separators; in the params column separate choices with commas, e.g. op: choice +,-,*"})
            else:
                items.append((n, dict(zip(BATCH_FIELDS, f))))
    return fmt, items, errors


def batch_add(store: Store, text: str, dry_run: bool = False, names: set[str] | None = None) -> dict[str, Any]:
    """Add tasks from text. Pass a shared `names` set when adding several sources in a row so duplicates across
    them are detected (and a dry run predicts the real run exactly)."""
    fmt, items, errors = parse_batch(text)
    total = len(items) + len(errors)  # records seen, before validation
    if names is None:
        names = {r["name"] for r in store.q("SELECT name FROM practice_tasks")}
    added = dups = 0
    for line, d in items:
        try:
            v = validate({**d, "check_type": d.get("check_type") or "succeeds"})
            if v["name"] in names:
                dups += 1
                continue
            if len(names) >= MAX_TASKS:
                raise TaskError(f"limit of {MAX_TASKS} tasks reached")
            if not dry_run:
                add_task(store, v)
            names.add(v["name"])
            added += 1
        except TaskError as e:
            errors.append({"line": line, "error": str(e)})
    errors.sort(key=lambda e: e["line"])
    return {"format": fmt, "total": total, "added": added, "duplicates": dups, "errors": errors[:20], "error_count": len(errors), "dry_run": dry_run}


def batch_add_many(store: Store, texts: list[str], dry_run: bool = False) -> dict[str, Any]:
    """Several sources (e.g. several files) in order, sharing duplicate detection. Per-source results + totals."""
    names = {r["name"] for r in store.q("SELECT name FROM practice_tasks")}
    results = []
    for t in texts:
        try:
            results.append(batch_add(store, t, dry_run, names))
        except TaskError as e:
            results.append({"format": "?", "total": 0, "added": 0, "duplicates": 0, "errors": [], "error_count": 0, "failed": str(e), "dry_run": dry_run})
    return {"results": results, "added": sum(r["added"] for r in results), "duplicates": sum(r["duplicates"] for r in results),
            "total": sum(r["total"] for r in results), "dry_run": dry_run}
