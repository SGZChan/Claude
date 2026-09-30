from __future__ import annotations

import ast
import operator as op
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..config import Settings
from ..memory.store import Store
from .registry import CONFIRM, SAFE, Registry, ToolError

_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Mod: op.mod,
        ast.Pow: op.pow, ast.USub: op.neg, ast.UAdd: op.pos, ast.FloorDiv: op.floordiv}


def safe_eval(expr: str) -> float | int:
    def ev(n: ast.AST):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            l, r = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(r) > 64:
                raise ToolError("exponent too large")
            return _OPS[type(n.op)](l, r)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ToolError("unsupported expression")
    try:
        return ev(ast.parse(expr.strip(), mode="eval").body)
    except ZeroDivisionError:
        raise ToolError("division by zero")
    except SyntaxError:
        raise ToolError("invalid expression")


def fmt_num(x: float | int) -> str:
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(round(x, 10)) if isinstance(x, float) else str(x)


def build_registry(settings: Settings, store: Store) -> Registry:
    reg = Registry()
    ws = settings.workspace.resolve()

    def in_ws(rel: str) -> Path:
        p = (ws / rel).resolve()
        if p != ws and ws not in p.parents:
            raise ToolError("path escapes the workspace")
        return p

    @reg.register("calculator", "evaluate an arithmetic expression", {"expression": "e.g. 17*23"})
    def calculator(expression: str) -> str:
        return fmt_num(safe_eval(str(expression)))

    @reg.register("get_time", "current local date and time", {})
    def get_time() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    @reg.register("notes_add", "save a note to memory", {"text": "note text"})
    def notes_add(text: str) -> str:
        store.x("INSERT INTO notes(text,created) VALUES(?,?)", (str(text)[:1000], time.time()))
        store.add_fact("note", str(text))
        return f"saved note: {str(text)[:80]}"

    @reg.register("notes_list", "list saved notes", {})
    def notes_list() -> str:
        rows = store.q("SELECT text FROM notes ORDER BY id DESC LIMIT 10")
        return "; ".join(r["text"] for r in rows) or "no notes yet"

    @reg.register("memory_search", "search memory for related notes and lessons", {"query": "search text"})
    def memory_search(query: str) -> str:
        hits = store.search_facts(str(query), k=3)
        return "; ".join(h["text"] for h in hits) or "nothing found"

    @reg.register("file_list", "list files in the workspace folder", {"path": "relative folder, '.' for root"})
    def file_list(path: str) -> str:
        p = in_ws(str(path))
        if not p.is_dir():
            raise ToolError("not a folder")
        return ", ".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())) or "(empty)"

    @reg.register("file_read", "read a text file from the workspace", {"path": "relative file path"})
    def file_read(path: str) -> str:
        p = in_ws(str(path))
        if not p.is_file():
            raise ToolError("no such file")
        return p.read_text(errors="replace")[:2000]

    @reg.register("file_write", "write a text file in the workspace", {"path": "relative file path", "content": "text"}, tier=CONFIRM)
    def file_write(path: str, content: str) -> str:
        p = in_ws(str(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        return f"wrote {len(str(content))} chars to {path}"

    @reg.register("web_fetch", "fetch text of an allow-listed web page", {"url": "https URL"}, tier=CONFIRM)
    def web_fetch(url: str) -> str:
        u = urllib.parse.urlparse(str(url))
        if u.scheme != "https" or u.hostname not in settings.web_allowlist:
            raise ToolError(f"host not allow-listed: {u.hostname}")
        with urllib.request.urlopen(str(url), timeout=15) as r:  # noqa: S310 (scheme+host checked above)
            return r.read(20000).decode("utf-8", "replace")[:2000]

    @reg.register("python_sandbox", "run a short Python snippet (isolated, 5s limit), returns stdout", {"code": "python code"}, tier=CONFIRM)
    def python_sandbox(code: str) -> str:
        try:
            r = subprocess.run([sys.executable, "-I", "-c", str(code)], capture_output=True, text=True, timeout=5, cwd=ws)
        except subprocess.TimeoutExpired:
            raise ToolError("timed out")
        return (r.stdout + r.stderr)[:2000] or "(no output)"

    _RO = {"ls", "cat", "head", "wc", "pwd", "date"}

    @reg.register("shell_readonly", "run an allow-listed read-only command: ls cat head wc pwd date", {"command": "e.g. ls -la"}, tier=CONFIRM)
    def shell_readonly(command: str) -> str:
        import shlex
        parts = shlex.split(str(command))
        if not parts or parts[0] not in _RO or any(x in {"|", ";", "&&", ">", "<"} for x in parts):
            raise ToolError("command not allowed")
        for a in parts[1:]:
            if not a.startswith("-"):
                in_ws(a)
        r = subprocess.run(parts, capture_output=True, text=True, timeout=5, cwd=ws)
        return (r.stdout + r.stderr)[:2000] or "(no output)"

    return reg
