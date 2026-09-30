from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Callable

from ..memory.store import Store
from ..tools.registry import Registry
from .catalog import BY_ID, CATALOG, PRESETS

if TYPE_CHECKING:
    from ..core import Laya


class FeatureError(Exception):
    pass


class FeatureManager:
    """Which features are on. Persisted in the kv table (`feature:<id>`); tools/behaviours consult it live."""

    def __init__(self, store: Store, registry: Registry) -> None:
        self.store, self.registry = store, registry
        self.laya: "Laya | None" = None
        self.jobs: dict[str, Callable[["Laya"], str]] = {}
        from .jobs import JOBS
        self.jobs.update(JOBS)
        self.apply()

    def bind(self, laya: "Laya") -> None:
        self.laya = laya
        if self.enabled("plugins"):
            self._load_plugins()

    # -- state ------------------------------------------------------------
    def enabled(self, fid: str) -> bool:
        v = self.store.get_kv(f"feature:{fid}")
        return (v == "1") if v else BY_ID[fid].default

    def _write(self, fid: str, on: bool) -> None:
        self.store.set_kv(f"feature:{fid}", "1" if on else "0")

    def apply(self) -> None:
        """Push the current on/off state into the tool registry."""
        self.registry.disabled_features = {f.id for f in CATALOG if not self.enabled(f.id)}
        self.registry.offline = self.enabled("offline_mode")

    def dependents(self, fid: str) -> list[str]:
        return [f.id for f in CATALOG if fid in f.requires]

    def set_enabled(self, fid: str, on: bool) -> dict[str, list[str]]:
        """Toggle a feature. Enabling pulls in what it requires; disabling switches off what depends on it."""
        if fid not in BY_ID:
            raise FeatureError(f"unknown feature '{fid}'")
        changed: list[str] = []

        def turn(f: str, val: bool) -> None:
            if self.enabled(f) != val:
                changed.append(f)
            self._write(f, val)

        if on:
            for r in BY_ID[fid].requires:
                turn(r, True)
            turn(fid, True)
        else:
            turn(fid, False)
            stack = self.dependents(fid)
            while stack:
                d = stack.pop()
                turn(d, False)
                stack += self.dependents(d)
        self.apply()
        if fid == "plugins" and on:
            self._load_plugins()
        return {"changed": changed}

    def apply_preset(self, name: str) -> list[str]:
        if name not in PRESETS:
            raise FeatureError(f"unknown preset '{name}'")
        want = set(PRESETS[name]["features"])
        for f in CATALOG:
            self._write(f.id, f.id in want)
        self.apply()
        if "plugins" in want:
            self._load_plugins()
        return sorted(want)

    def _load_plugins(self) -> list[dict[str, Any]]:
        loader = getattr(self.registry, "plugin_loader", None)
        return loader() if loader else []

    def plugins(self) -> list[dict[str, Any]]:
        return self._load_plugins() if self.enabled("plugins") else []

    # -- description for the UI ------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        out = []
        for f in CATALOG:
            tools = [{"name": t.name, "tier": t.tier, "network": t.network} for t in self.registry.tools.values() if t.feature == f.id]
            last = self.store.get_kv(f"job_result:{f.id}")
            out.append({
                "id": f.id, "name": f.name, "description": f.description, "category": f.category, "kind": f.kind,
                "enabled": self.enabled(f.id), "default": f.default, "requires": list(f.requires),
                "dependents": self.dependents(f.id), "risk": f.risk, "example": f.example, "tools": tools,
                "blocked_by_offline": bool(tools) and all(t["network"] for t in tools) and self.enabled("offline_mode"),
                "job": {"interval": f.interval, "last": json.loads(last) if last else None} if f.job else None,
            })
        return out

    # -- background jobs --------------------------------------------------
    def run_job(self, fid: str, force: bool = False, now: float | None = None) -> str | None:
        f = BY_ID[fid]
        if not f.job or self.laya is None or not self.enabled(fid):
            return None
        now = now or time.time()
        last = self.store.get_kv(f"job_last:{fid}")
        if not force and last and now - float(last) < f.interval:
            return None
        self.store.set_kv(f"job_last:{fid}", str(now))
        try:
            msg, ok = self.jobs[f.job](self.laya), True
        except Exception as e:  # a failing job must not kill the scheduler
            msg, ok = f"{type(e).__name__}: {e}", False
        self.store.set_kv(f"job_result:{fid}", json.dumps({"ts": now, "ok": ok, "message": msg[:300]}))
        return msg

    def run_due_jobs(self, now: float | None = None) -> dict[str, str]:
        if self.store.get_kv("killed") == "1":
            return {}
        res = {}
        for f in CATALOG:
            if f.job:
                m = self.run_job(f.id, now=now)
                if m is not None:
                    res[f.id] = m
        return res
