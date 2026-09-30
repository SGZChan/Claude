"""Shared helpers for tool modules."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..memory.store import Store
from .registry import Registry, ToolError

TEXT_EXT = {".txt", ".md", ".rst", ".py", ".js", ".ts", ".tsx", ".json", ".csv", ".log", ".yml", ".yaml", ".toml", ".html", ".css", ".ini", ".cfg", ".eml", ".ics"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist"}
STOP = set("the a an and or of to in on for is are was were be been it this that with as at by from we you they i not but if then so".split())


@dataclass
class Ctx:
    settings: Settings
    store: Store
    reg: Registry
    ws: Path

    def in_ws(self, rel: str) -> Path:
        p = (self.ws / str(rel)).resolve()
        if p != self.ws and self.ws not in p.parents:
            raise ToolError("path escapes the workspace")
        return p

    def text_files(self, rel: str = ".", exts: set[str] | None = None) -> list[Path]:
        base = self.in_ws(rel)
        if base.is_file():
            return [base]
        out = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and not (set(p.relative_to(self.ws).parts[:-1]) & SKIP_DIRS) and p.suffix.lower() in (exts or TEXT_EXT):
                out.append(p)
        return out[:500]

    def rel(self, p: Path) -> str:
        return p.relative_to(self.ws).as_posix()


def read_text(p: Path, limit: int = 200_000) -> str:
    if not p.is_file():
        raise ToolError("no such file")
    return p.read_text(errors="replace")[:limit]


def summarize(text: str, n: int = 3) -> str:
    """Tiny extractive summary: the n highest-scoring sentences, in original order."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if len(s.strip()) > 20]
    if len(sents) <= n:
        return " ".join(sents) or text.strip()[:300]
    freq = Counter(w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP)
    score = lambda s: sum(freq[w] for w in re.findall(r"[a-z]{3,}", s.lower())) / (len(s.split()) ** 0.5 + 1)  # noqa: E731
    top = sorted(sorted(range(len(sents)), key=lambda i: -score(sents[i]))[:n])
    return " ".join(sents[i] for i in top)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.out.append(data.strip())


def strip_html(html: str) -> str:
    p = _Text()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.out))


def chunk_text(text: str, size: int = 500) -> list[str]:
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        while len(para) > size:  # hard-split very long paragraphs
            chunks.append(para[:size])
            para = para[size:]
        if len(cur) + len(para) + 1 > size and cur:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{para}".strip()
    if cur:
        chunks.append(cur)
    return chunks


Install = Callable[[Ctx], None]
