"""Background scheduler: user schedules (Schedules page) + feature jobs (reminders, auto-index, ...)."""
from __future__ import annotations

import threading
import time

from .core import Laya


class Scheduler:
    def __init__(self, laya: Laya, period: float = 15.0) -> None:
        self.laya, self.period = laya, period
        self._stop = threading.Event()

    def tick(self, now: float | None = None) -> dict:
        """One pass. Returns what fired (also used directly by tests)."""
        now = now or time.time()
        laya, fired = self.laya, []
        if laya.store.get_kv("killed") == "1":
            return {"schedules": [], "jobs": {}}
        if laya.features.enabled("scheduler"):
            for s in laya.store.q("SELECT * FROM schedules WHERE enabled=1"):
                if now - (s["last_run"] or 0) >= s["interval_s"]:
                    laya.store.x("UPDATE schedules SET last_run=? WHERE id=?", (now, s["id"]))
                    laya.runner.start(s["goal"], source="schedule")
                    fired.append(s["id"])
        return {"schedules": fired, "jobs": laya.features.run_due_jobs(now)}

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.period):
                try:
                    self.tick()
                except Exception:  # keep the thread alive
                    pass

        threading.Thread(target=loop, daemon=True, name="laya-scheduler").start()

    def stop(self) -> None:
        self._stop.set()
