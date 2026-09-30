from __future__ import annotations

import ast
import operator as op
import time

from ..config import Settings
from ..memory.store import Store
from .helpers import Ctx
from .registry import Registry, ToolError

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
    from . import assistant, comms, data, dev, files, kb, plugins, utility, web

    reg = Registry()
    ctx = Ctx(settings, store, reg, settings.workspace.resolve())

    @reg.register("calculator", "evaluate an arithmetic expression (math, sum, multiply, percent)", {"expression": "e.g. 17*23"}, feature="calculator")
    def calculator(expression: str) -> str:
        return fmt_num(safe_eval(str(expression)))

    @reg.register("get_time", "current local date and time", {}, feature="calculator")
    def get_time() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    @reg.register("notes_add", "save a note to memory (remember, write down)", {"text": "note text"}, feature="notes")
    def notes_add(text: str) -> str:
        store.x("INSERT INTO notes(text,created) VALUES(?,?)", (str(text)[:1000], time.time()))
        store.add_fact("note", str(text))
        return f"saved note: {str(text)[:80]}"

    @reg.register("notes_list", "list saved notes", {}, feature="notes")
    def notes_list() -> str:
        rows = store.q("SELECT text FROM notes ORDER BY id DESC LIMIT 10")
        return "; ".join(r["text"] for r in rows) or "no notes yet"

    @reg.register("memory_search", "search memory for related notes and lessons", {"query": "search text"}, feature="notes")
    def memory_search(query: str) -> str:
        hits = store.search_facts(str(query), k=3)
        return "; ".join(h["text"] for h in hits) or "nothing found"

    for mod in (assistant, files, web, data, dev, comms, utility, kb, plugins):
        mod.install(ctx)
    return reg
