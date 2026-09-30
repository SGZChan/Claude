from __future__ import annotations

import asyncio
import io
import json
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..core import Laya
from ..features import CATALOG, PRESETS, FeatureError
from ..scheduler import Scheduler
from ..tools.assistant import brief_text, fmt_ts
from ..learning.curriculum import practice
from ..learning.export import export_jsonl
from ..learning.feedback import apply_feedback
from . import metrics

DIST = Path(__file__).resolve().parents[3] / "dashboard" / "dist"


class GoalIn(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class ApproveIn(BaseModel):
    approve: bool


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    correction: str = ""


class EnabledIn(BaseModel):
    enabled: bool


class FactIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: str = "note"


class TierIn(BaseModel):
    tier: str = Field(pattern="^(safe|confirm|blocked)$")


class ScheduleIn(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    interval_s: int = Field(ge=30)


class PracticeIn(BaseModel):
    n: int = Field(default=6, ge=1, le=30)


class KillIn(BaseModel):
    on: bool


def create_app(laya: Laya | None = None, run_scheduler: bool = False) -> FastAPI:
    laya = laya or Laya()
    app = FastAPI(title="Laya", version="0.1.0")
    app.state.laya = laya
    store = laya.store

    def need_run(rid: int) -> dict[str, Any]:
        r = store.get_run(rid)
        if not r:
            raise HTTPException(404, "run not found")
        return r

    # -- runs -------------------------------------------------------------
    @app.post("/api/runs", status_code=201)
    def start_run(body: GoalIn):
        if store.get_kv("killed") == "1":
            raise HTTPException(423, "kill switch is on")
        return {"id": laya.runner.start(body.goal.strip())}

    @app.get("/api/runs")
    def list_runs(q: str = "", limit: int = 100):
        return store.list_runs(min(limit, 500), q)

    @app.get("/api/runs/{rid}")
    def get_run(rid: int):
        r = need_run(rid)
        r["pending_approval"] = laya.runner.pending(rid)
        return r

    @app.get("/api/runs/{rid}/stream")
    async def stream(rid: int):
        need_run(rid)

        async def gen():
            sent = 0
            while True:
                r = store.get_run(rid)
                assert r
                for ev in r["events"][sent:]:
                    yield f"data: {json.dumps(ev)}\n\n"
                sent = len(r["events"])
                if r["status"] != "running":
                    yield f"event: done\ndata: {json.dumps({'status': r['status']})}\n\n"
                    return
                await asyncio.sleep(0.15)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/runs/{rid}/approve")
    def approve(rid: int, body: ApproveIn):
        if not laya.runner.approve(rid, body.approve):
            raise HTTPException(409, "no approval pending")
        return {"ok": True}

    @app.post("/api/runs/{rid}/stop")
    def stop(rid: int):
        return {"ok": laya.runner.stop(rid)}

    @app.post("/api/runs/{rid}/feedback")
    def feedback(rid: int, body: FeedbackIn):
        apply_feedback(store, laya.skills, need_run(rid), body.rating, body.correction)
        return {"ok": True}

    # -- metrics / skills / memory ---------------------------------------
    @app.get("/api/metrics/overview")
    def overview():
        return metrics.overview(store)

    @app.get("/api/skills")
    def skills():
        return laya.skills.list()

    @app.patch("/api/skills/{sid}")
    def patch_skill(sid: int, body: EnabledIn):
        if not laya.skills.get(sid):
            raise HTTPException(404, "skill not found")
        laya.skills.set_enabled(sid, body.enabled)
        return laya.skills.get(sid)

    @app.delete("/api/skills/{sid}", status_code=204)
    def del_skill(sid: int):
        laya.skills.delete(sid)

    @app.get("/api/memory")
    def memory(q: str = "", kind: str = ""):
        if q:
            return store.search_facts(q, k=25, kinds=(kind,) if kind else None, min_sim=0.07)
        return store.list_facts(kind or None)

    @app.post("/api/memory", status_code=201)
    def add_memory(body: FactIn):
        return {"id": store.add_fact(body.kind, body.text)}

    @app.delete("/api/memory/{fid}", status_code=204)
    def del_memory(fid: int):
        store.delete_fact(fid)

    # -- tools ------------------------------------------------------------
    @app.get("/api/tools")
    def tools():
        stats = {r["tool"]: r for r in store.q("SELECT * FROM tool_stats")}
        return [{**t, "calls": stats.get(t["name"], {}).get("calls", 0), "errors": stats.get(t["name"], {}).get("errors", 0)}
                for t in laya.registry.specs()]

    @app.patch("/api/tools/{name}")
    def set_tier(name: str, body: TierIn):
        if not laya.registry.get(name):
            raise HTTPException(404, "tool not found")
        laya.registry.set_tier(name, body.tier)
        return {"ok": True}

    # -- learning ---------------------------------------------------------
    @app.get("/api/learning")
    def learning():
        last = store.get_kv("last_practice")
        return {"lessons": store.list_facts("lesson", 50), "corrections": store.list_facts("correction", 50),
                "last_practice": json.loads(last) if last else None,
                "candidates": store.q("SELECT shape,count FROM candidates ORDER BY count DESC LIMIT 20"),
                "promote_after": laya.settings.promote_after}

    @app.post("/api/learning/practice")
    def do_practice(body: PracticeIn):
        return practice(laya, body.n)

    @app.get("/api/learning/export.jsonl", response_class=PlainTextResponse)
    def export():
        return export_jsonl(store)

    # -- schedules --------------------------------------------------------
    @app.get("/api/schedules")
    def schedules():
        return store.q("SELECT * FROM schedules ORDER BY id DESC")

    @app.post("/api/schedules", status_code=201)
    def add_schedule(body: ScheduleIn):
        return {"id": store.x("INSERT INTO schedules(goal,interval_s,last_run) VALUES(?,?,?)", (body.goal, body.interval_s, time.time()))}

    @app.patch("/api/schedules/{sid}")
    def patch_schedule(sid: int, body: EnabledIn):
        store.x("UPDATE schedules SET enabled=? WHERE id=?", (int(body.enabled), sid))
        return {"ok": True}

    @app.delete("/api/schedules/{sid}", status_code=204)
    def del_schedule(sid: int):
        store.x("DELETE FROM schedules WHERE id=?", (sid,))

    # -- system -----------------------------------------------------------
    @app.get("/api/system")
    def system():
        s = laya.settings
        return {"llm": laya.llm.info(), "killed": store.get_kv("killed") == "1", "max_steps": s.max_steps,
                "run_timeout": s.run_timeout, "promote_after": s.promote_after, "data_dir": str(s.data_dir.resolve()),
                "web_allowlist": s.web_allowlist, "version": app.version}

    @app.post("/api/system/kill")
    def kill(body: KillIn):
        store.set_kv("killed", "1" if body.on else "0")
        if body.on:
            for rid in list(laya.runner.handles):
                laya.runner.stop(rid)
        return {"killed": body.on}

    # -- features ---------------------------------------------------------
    @app.get("/api/features")
    def features():
        cats = list(dict.fromkeys(f.category for f in CATALOG))
        return {"features": laya.features.list(), "categories": cats,
                "presets": [{"id": k, "label": v["label"], "description": v["description"], "count": len(v["features"])} for k, v in PRESETS.items()]}

    @app.patch("/api/features/{fid}")
    def set_feature(fid: str, body: EnabledIn):
        try:
            return laya.features.set_enabled(fid, body.enabled)
        except FeatureError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/features/preset/{name}")
    def preset(name: str):
        try:
            return {"enabled": laya.features.apply_preset(name)}
        except FeatureError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/features/{fid}/run")
    def run_job(fid: str):
        msg = laya.features.run_job(fid, force=True)
        if msg is None:
            raise HTTPException(409, "feature has no job, or is turned off")
        return {"message": msg}

    @app.get("/api/plugins")
    def plugins():
        return {"enabled": laya.features.enabled("plugins"), "dir": str((laya.settings.data_dir / "plugins").resolve()), "plugins": laya.features.plugins()}

    @app.get("/api/backup.zip")
    def backup():
        if not laya.features.enabled("backup"):
            raise HTTPException(403, "backup feature is off")
        buf = io.BytesIO()
        with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            import sqlite3
            dst = sqlite3.connect(f"{td}/laya.db")
            with store._lock:
                store.db.backup(dst)
            dst.close()
            z.write(f"{td}/laya.db", "laya.db")
            for f in laya.settings.workspace.rglob("*"):
                if f.is_file():
                    z.write(f, f"workspace/{f.relative_to(laya.settings.workspace).as_posix()}")
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=laya-backup-{time.strftime('%Y%m%d-%H%M')}.zip"})

    @app.get("/api/assistant/today")
    def today():
        f = laya.features
        return {
            "brief": brief_text(store) if f.enabled("daily_brief") else None,
            "todos": store.q("SELECT id,text,due FROM todos WHERE done=0 ORDER BY id LIMIT 20") if f.enabled("todos") else None,
            "reminders": [{**r, "when": fmt_ts(r["due"])} for r in store.q("SELECT id,text,due FROM reminders WHERE fired=0 ORDER BY due LIMIT 20")] if f.enabled("reminders") else None,
            "alerts": store.q("SELECT id,text FROM facts WHERE kind='reminder' ORDER BY id DESC LIMIT 5") if f.enabled("reminders") else None,
        }

    @app.post("/api/todos/{tid}/done")
    def todo_done(tid: int):
        store.x("UPDATE todos SET done=1 WHERE id=?", (tid,))
        return {"ok": True}

    # -- scheduler thread -------------------------------------------------
    app.state.scheduler = Scheduler(laya)
    if run_scheduler:
        app.state.scheduler.start()

    # -- dashboard --------------------------------------------------------
    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (DIST / path).resolve()
            if path and f.is_file() and DIST.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(DIST / "index.html")

    return app
