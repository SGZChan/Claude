from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .vector import embed, from_blob, to_blob

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT, status TEXT, answer TEXT, via TEXT,
  steps TEXT, events TEXT, started REAL, ended REAL, latency REAL, feedback INTEGER DEFAULT 0,
  error TEXT, skill_id INTEGER, shape TEXT);
CREATE TABLE IF NOT EXISTS facts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, text TEXT, emb BLOB, score REAL DEFAULT 1.0, created REAL);
CREATE TABLE IF NOT EXISTS skills(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, shape TEXT UNIQUE, steps TEXT, successes INTEGER DEFAULT 0,
  failures INTEGER DEFAULT 0, uses INTEGER DEFAULT 0, score REAL DEFAULT 1.0, enabled INTEGER DEFAULT 1,
  created REAL, last_used REAL);
CREATE TABLE IF NOT EXISTS candidates(
  key TEXT PRIMARY KEY, shape TEXT, steps TEXT, count INTEGER DEFAULT 0, updated REAL);
CREATE TABLE IF NOT EXISTS schedules(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT, interval_s INTEGER, enabled INTEGER DEFAULT 1, last_run REAL);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, created REAL);
CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, done INTEGER DEFAULT 0, due TEXT, created REAL);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, due REAL, fired INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, mood TEXT, created REAL);
CREATE TABLE IF NOT EXISTS kb_files(path TEXT PRIMARY KEY, mtime REAL, fact_ids TEXT);
CREATE TABLE IF NOT EXISTS practice_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, template TEXT, params TEXT DEFAULT '', check_type TEXT,
  check_value TEXT DEFAULT '', tolerance REAL DEFAULT 0.001, enabled INTEGER DEFAULT 1, runs INTEGER DEFAULT 0,
  passes INTEGER DEFAULT 0, last_fail TEXT DEFAULT '', created REAL);
CREATE TABLE IF NOT EXISTS imported_traces(hash TEXT PRIMARY KEY, created REAL);
CREATE TABLE IF NOT EXISTS tool_stats(tool TEXT PRIMARY KEY, calls INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # -- low level --------------------------------------------------------
    def q(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def x(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid or 0

    # -- kv ---------------------------------------------------------------
    def get_kv(self, key: str, default: str = "") -> str:
        r = self.q("SELECT value FROM kv WHERE key=?", (key,))
        return r[0]["value"] if r else default

    def set_kv(self, key: str, value: str) -> None:
        self.x("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # -- facts / vector memory -------------------------------------------
    def add_fact(self, kind: str, text: str, score: float = 1.0) -> int:
        text = text.strip()[:500]
        dup = self.q("SELECT id FROM facts WHERE kind=? AND text=?", (kind, text))
        if dup:
            return dup[0]["id"]
        return self.x("INSERT INTO facts(kind,text,emb,score,created) VALUES(?,?,?,?,?)",
                      (kind, text, to_blob(embed(text)), score, time.time()))

    def search_facts(self, query: str, k: int = 3, kinds: tuple[str, ...] | None = None, min_sim: float = 0.15) -> list[dict[str, Any]]:
        qv = embed(query)
        rows = self.q("SELECT id,kind,text,emb,score,created FROM facts" + (
            " WHERE kind IN (%s)" % ",".join("?" * len(kinds)) if kinds else ""), tuple(kinds or ()))
        scored = []
        for r in rows:
            sim = float(qv @ from_blob(r.pop("emb")))
            if sim >= min_sim and r["score"] > 0:
                r["similarity"] = round(sim, 3)
                scored.append(r)
        scored.sort(key=lambda r: r["similarity"] * r["score"], reverse=True)
        return scored[:k]

    def list_facts(self, kind: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if kind:
            return self.q("SELECT id,kind,text,score,created FROM facts WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
        return self.q("SELECT id,kind,text,score,created FROM facts ORDER BY id DESC LIMIT ?", (limit,))

    def delete_fact(self, fid: int) -> None:
        self.x("DELETE FROM facts WHERE id=?", (fid,))

    # -- tool stats -------------------------------------------------------
    def record_tool(self, tool: str, ok: bool) -> None:
        self.x("INSERT INTO tool_stats(tool,calls,errors) VALUES(?,1,?) ON CONFLICT(tool) DO UPDATE SET "
               "calls=calls+1, errors=errors+excluded.errors", (tool, 0 if ok else 1))

    # -- runs -------------------------------------------------------------
    def create_run(self, goal: str) -> int:
        return self.x("INSERT INTO runs(goal,status,steps,events,started) VALUES(?,?,?,?,?)",
                      (goal, "running", "[]", "[]", time.time()))

    def update_run(self, rid: int, **fields: Any) -> None:
        for k in ("steps", "events"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        cols = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), rid))

    def get_run(self, rid: int) -> dict[str, Any] | None:
        r = self.q("SELECT * FROM runs WHERE id=?", (rid,))
        if not r:
            return None
        run = r[0]
        run["steps"] = json.loads(run["steps"] or "[]")
        run["events"] = json.loads(run["events"] or "[]")
        return run

    def list_runs(self, limit: int = 100, q: str = "") -> list[dict[str, Any]]:
        sql = "SELECT id,goal,status,answer,via,started,latency,feedback,skill_id FROM runs"
        args: tuple = ()
        if q:
            sql += " WHERE goal LIKE ? OR answer LIKE ?"
            args = (f"%{q}%", f"%{q}%")
        return self.q(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))
