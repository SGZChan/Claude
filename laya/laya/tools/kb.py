"""Personal knowledge base: index workspace documents into vector memory and answer from them (RAG)."""
from __future__ import annotations

import json

from .helpers import Ctx, chunk_text, read_text
from .registry import ToolError


def ingest(ctx: Ctx, path: str = ".") -> dict:
    """Index new/changed files, drop chunks of changed ones. Returns counts."""
    store = ctx.store
    new = updated = chunks = 0
    for p in ctx.text_files(path):
        rel, mtime = ctx.rel(p), p.stat().st_mtime
        row = store.q("SELECT mtime,fact_ids FROM kb_files WHERE path=?", (rel,))
        if row and row[0]["mtime"] >= mtime:
            continue
        for fid in json.loads(row[0]["fact_ids"]) if row else []:
            store.delete_fact(fid)
        ids = [store.add_fact("kb", f"[{rel}] {c}") for c in chunk_text(read_text(p))]
        store.x("INSERT INTO kb_files(path,mtime,fact_ids) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, fact_ids=excluded.fact_ids",
                (rel, mtime, json.dumps(ids)))
        updated += bool(row)
        new += not row
        chunks += len(ids)
    return {"new_files": new, "updated_files": updated, "chunks": chunks}


def install(ctx: Ctx) -> None:
    reg, store = ctx.reg, ctx.store

    @reg.register("kb_ingest", "index documents from the workspace into the knowledge base", {"path": "folder or file, '.' for all"}, feature="knowledge_base", optional=("path",))
    def kb_ingest(path: str = ".") -> str:
        r = ingest(ctx, str(path))
        return f"indexed {r['new_files']} new and {r['updated_files']} updated files ({r['chunks']} chunks)"

    @reg.register("kb_ask", "answer a question from the indexed knowledge base and cite sources (what do my documents say)", {"question": "question"}, feature="knowledge_base")
    def kb_ask(question: str) -> str:
        hits = store.search_facts(str(question), k=3, kinds=("kb",), min_sim=0.07)
        if not hits:
            raise ToolError("nothing relevant indexed; run kb_ingest first")
        return "\n".join(h["text"][:300] for h in hits)

    @reg.register("kb_sources", "list documents in the knowledge base", {}, feature="knowledge_base")
    def kb_sources() -> str:
        rows = store.q("SELECT path,fact_ids FROM kb_files ORDER BY path")
        return ", ".join(f"{r['path']} ({len(json.loads(r['fact_ids']))} chunks)" for r in rows) or "knowledge base is empty"
