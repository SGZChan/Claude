"""Runs agent goals in background threads; brokers approvals and stop requests."""
from __future__ import annotations

import threading
from typing import Any

from .loop import Agent


class _Handle:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.decision = threading.Event()
        self.approved = False
        self.pending: dict[str, Any] | None = None


class Runner:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.handles: dict[int, _Handle] = {}

    def start(self, goal: str, source: str = "user") -> int:
        rid = self.agent.store.create_run(goal)
        h = _Handle()
        self.handles[rid] = h

        def approver(tool: str, args: dict[str, Any]) -> bool:
            h.pending, h.approved = {"tool": tool, "args": args}, False
            h.decision.clear()
            h.decision.wait(self.agent.settings.approval_timeout)
            h.pending = None
            return h.approved and not h.stop.is_set()

        def work() -> None:
            try:
                self.agent.run(goal, run_id=rid, approver=approver, stop=h.stop, source=source)
            except Exception as e:  # never leave a run stuck in "running"
                self.agent.store.update_run(rid, status="failed", error=f"{type(e).__name__}: {e}")
            finally:
                self.handles.pop(rid, None)

        threading.Thread(target=work, daemon=True, name=f"laya-run-{rid}").start()
        return rid

    def approve(self, rid: int, ok: bool) -> bool:
        h = self.handles.get(rid)
        if not h or h.pending is None:
            return False
        h.approved = ok
        h.decision.set()
        return True

    def stop(self, rid: int) -> bool:
        h = self.handles.get(rid)
        if not h:
            return False
        h.stop.set()
        h.decision.set()
        return True

    def pending(self, rid: int) -> dict[str, Any] | None:
        h = self.handles.get(rid)
        return h.pending if h else None
