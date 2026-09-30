from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..core import Laya
from ..learning import tasks as T
from ..learning.curriculum import practice


class TaskIn(BaseModel):
    name: str = Field(max_length=80)
    template: str = Field(max_length=300)
    params: str = Field(default="", max_length=1000)
    check_type: Literal["succeeds", "equals", "contains", "regex", "expr", "tool"] = "succeeds"
    check_value: str = Field(default="", max_length=300)
    tolerance: float = Field(default=0.001, ge=0, le=1)
    enabled: bool = True


class EnabledIn(BaseModel):
    enabled: bool


class RunIn(BaseModel):
    n: int = Field(default=3, ge=1, le=20)


class BatchIn(BaseModel):
    text: str = Field(default="", max_length=500_000)
    texts: list[str] = Field(default_factory=list, max_length=50)  # several sources at once (e.g. several files)
    dry_run: bool = False


class ImportIn(BaseModel):
    tasks: list[dict[str, Any]] = Field(max_length=T.MAX_TASKS)


def register(app: FastAPI, laya: Laya) -> None:
    store = laya.store

    def gate() -> None:
        if not laya.features.enabled("custom_practice"):
            raise HTTPException(403, "the 'Custom practice tasks' feature is off")

    def guard(fn, *a):
        try:
            return fn(*a)
        except T.TaskError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/practice/tasks")
    def list_tasks():
        gate()
        return T.list_tasks(store)

    @app.post("/api/practice/tasks", status_code=201)
    def add_task(body: TaskIn):
        gate()
        return {"id": guard(T.add_task, store, body.model_dump())}

    @app.put("/api/practice/tasks/{tid}")
    def update_task(tid: int, body: TaskIn):
        gate()
        guard(T.update_task, store, tid, body.model_dump())
        return {"ok": True}

    @app.patch("/api/practice/tasks/{tid}")
    def toggle_task(tid: int, body: EnabledIn):
        gate()
        store.x("UPDATE practice_tasks SET enabled=? WHERE id=?", (int(body.enabled), tid))
        return {"ok": True}

    @app.delete("/api/practice/tasks/{tid}", status_code=204)
    def delete_task(tid: int):
        gate()
        store.x("DELETE FROM practice_tasks WHERE id=?", (tid,))

    @app.post("/api/practice/tasks/{tid}/run")
    def run_task(tid: int, body: RunIn):
        gate()
        if store.get_kv("killed") == "1":
            raise HTTPException(423, "kill switch is on")
        return guard(practice, laya, body.n, None, tid)

    @app.post("/api/practice/starter")
    def starter():
        gate()
        return {"added": T.add_starter_pack(store)}

    @app.get("/api/practice/export")
    def export():
        gate()
        return T.export_tasks(store)

    @app.post("/api/practice/batch")
    def batch(body: BatchIn):
        gate()
        if body.texts:
            if any(len(t) > 500_000 for t in body.texts):
                raise HTTPException(422, "a source is over 500,000 characters")
            return T.batch_add_many(store, body.texts, body.dry_run)
        if not body.text.strip():
            raise HTTPException(422, "nothing to add: paste some tasks or choose a file")
        return guard(T.batch_add, store, body.text, body.dry_run)

    @app.post("/api/practice/import")
    def import_(body: ImportIn):
        gate()
        return T.import_tasks(store, body.tasks)
