from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

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

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "params": self.params, "tier": self.tier}


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, name: str, description: str, params: dict[str, str] | None = None, tier: str = SAFE):
        def deco(fn: Callable[..., str]) -> Callable[..., str]:
            self.tools[name] = Tool(name, description, params or {}, fn, tier)
            return fn
        return deco

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self.tools.values()]

    def set_tier(self, name: str, tier: str) -> None:
        if name in self.tools and tier in (SAFE, CONFIRM, BLOCKED):
            self.tools[name].tier = tier

    def prompt_block(self) -> str:
        lines = []
        for t in self.tools.values():
            if t.tier == BLOCKED:
                continue
            args = ", ".join(t.params)
            lines.append(f"- {t.name}({args}): {t.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            raise ToolError(f"unknown tool '{name}'")
        if not isinstance(args, dict):
            raise ToolError("args must be an object")
        missing = [p for p in tool.params if p not in args]
        if missing:
            raise ToolError(f"missing args: {', '.join(missing)}")
        try:
            return str(tool.fn(**{k: args[k] for k in tool.params}))
        except ToolError:
            raise
        except Exception as e:  # tool bugs must not crash the agent
            raise ToolError(f"{type(e).__name__}: {e}") from e
