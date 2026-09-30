from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..memory.vector import embed

SAFE, CONFIRM, BLOCKED = "safe", "confirm", "blocked"


class ToolError(Exception):
    pass


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]  # arg name -> short description
    fn: Callable[..., str]
    tier: str = SAFE
    feature: str = "core"
    network: bool = False
    optional: tuple[str, ...] = ()

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "params": self.params, "tier": self.tier,
                "feature": self.feature, "network": self.network, "optional": list(self.optional)}


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)
    disabled_features: set[str] = field(default_factory=set)
    offline: bool = False
    _emb: dict[str, Any] = field(default_factory=dict, repr=False)

    def register(self, name: str, description: str, params: dict[str, str] | None = None, tier: str = SAFE,
                 feature: str = "core", network: bool = False, optional: tuple[str, ...] = ()):
        def deco(fn: Callable[..., str]) -> Callable[..., str]:
            self.tools[name] = Tool(name, description, params or {}, fn, tier, feature, network, optional)
            self._emb.pop(name, None)
            return fn
        return deco

    def unregister_feature(self, feature: str) -> None:
        for n in [n for n, t in self.tools.items() if t.feature == feature]:
            del self.tools[n]

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def why_unavailable(self, tool: Tool) -> str:
        if tool.feature in self.disabled_features:
            return f"tool '{tool.name}' is off: feature '{tool.feature}' is disabled"
        if tool.network and self.offline:
            return f"tool '{tool.name}' needs the network but offline mode is on"
        if tool.tier == BLOCKED:
            return f"tool '{tool.name}' is blocked"
        return ""

    def available(self, tool: Tool) -> bool:
        return not self.why_unavailable(tool)

    def specs(self) -> list[dict[str, Any]]:
        out = []
        for t in self.tools.values():
            s = t.spec()
            s["available"] = self.available(t)
            out.append(s)
        return out

    def set_tier(self, name: str, tier: str) -> None:
        if name in self.tools and tier in (SAFE, CONFIRM, BLOCKED):
            self.tools[name].tier = tier

    def prompt_block(self, goal: str = "", k: int = 10) -> str:
        """Tools shown to the model. A 0.5B model has a tiny context, so with many tools enabled only the
        k most relevant to the goal are listed (hashed-embedding similarity; ties keep registration order)."""
        avail = [t for t in self.tools.values() if self.available(t)]
        if goal and len(avail) > k:
            q = embed(goal)

            def sim(t: Tool) -> float:
                if t.name not in self._emb:
                    self._emb[t.name] = embed(f"{t.name.replace('_', ' ')} {t.description}")
                return float(q @ self._emb[t.name])

            ranked = sorted(range(len(avail)), key=lambda i: (-sim(avail[i]), i))[:k]
            avail = [avail[i] for i in sorted(ranked)]
        lines = []
        for t in avail:
            args = ", ".join(p + ("?" if p in t.optional else "") for p in t.params)
            lines.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            raise ToolError(f"unknown tool '{name}'")
        if reason := self.why_unavailable(tool):
            raise ToolError(reason)
        if not isinstance(args, dict):
            raise ToolError("args must be an object")
        missing = [p for p in tool.params if p not in args and p not in tool.optional]
        if missing:
            raise ToolError(f"missing args: {', '.join(missing)}")
        try:
            return str(tool.fn(**{k: args[k] for k in tool.params if k in args}))
        except ToolError:
            raise
        except Exception as e:  # tool bugs must not crash the agent
            raise ToolError(f"{type(e).__name__}: {e}") from e
