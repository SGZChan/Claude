"""File & document helper tools (all confined to the workspace)."""
from __future__ import annotations

import re

from .helpers import Ctx, read_text, summarize
from .registry import CONFIRM, ToolError


def install(ctx: Ctx) -> None:
    reg = ctx.reg

    @reg.register("file_list", "list files in the workspace folder", {"path": "relative folder, '.' for root"}, feature="file_helper")
    def file_list(path: str) -> str:
        p = ctx.in_ws(str(path))
        if not p.is_dir():
            raise ToolError("not a folder")
        return ", ".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())) or "(empty)"

    @reg.register("file_read", "read a text file from the workspace", {"path": "relative file path"}, feature="file_helper")
    def file_read(path: str) -> str:
        return read_text(ctx.in_ws(str(path)))[:2000]

    @reg.register("file_write", "write a text file in the workspace", {"path": "relative file path", "content": "text"}, tier=CONFIRM, feature="file_helper")
    def file_write(path: str, content: str) -> str:
        p = ctx.in_ws(str(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        return f"wrote {len(str(content))} chars to {path}"

    @reg.register("file_search", "find text inside workspace files (grep, find in files)", {"query": "text to find"}, feature="file_helper")
    def file_search(query: str) -> str:
        q = str(query).lower()
        hits = []
        for p in ctx.text_files():
            for i, line in enumerate(read_text(p).splitlines(), 1):
                if q in line.lower():
                    hits.append(f"{ctx.rel(p)}:{i}: {line.strip()[:100]}")
                    if len(hits) >= 10:
                        return "\n".join(hits)
        return "\n".join(hits) or "no matches"

    @reg.register("file_summarize", "short extractive summary of a text file (summarise document)", {"path": "relative file path"}, feature="file_helper")
    def file_summarize(path: str) -> str:
        return summarize(read_text(ctx.in_ws(str(path)))) or "(empty file)"

    @reg.register("file_extract", "pull emails, urls, numbers or dates out of a file", {"path": "relative file path", "kind": "emails | urls | numbers | dates"}, feature="file_helper")
    def file_extract(path: str, kind: str) -> str:
        pats = {"emails": r"[\w.+-]+@[\w-]+\.[\w.-]+", "urls": r"https?://[^\s<>\"')]+", "numbers": r"-?\d+(?:\.\d+)?", "dates": r"\d{4}-\d{2}-\d{2}"}
        if kind not in pats:
            raise ToolError("kind must be emails, urls, numbers or dates")
        found = list(dict.fromkeys(re.findall(pats[kind], read_text(ctx.in_ws(str(path))))))
        return ", ".join(found[:30]) or "none found"

    @reg.register("file_stats", "line, word and character counts of a file", {"path": "relative file path"}, feature="file_helper")
    def file_stats(path: str) -> str:
        t = read_text(ctx.in_ws(str(path)))
        return f"{len(t.splitlines())} lines, {len(t.split())} words, {len(t)} chars"
