from __future__ import annotations

from typing import Any, Protocol


class LLM(Protocol):
    name: str

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None, task: str = "act", max_tokens: int = 256) -> str:
        """Return model text. `schema` (JSON schema) requests constrained JSON output.
        `task` is a hint ("act" | "reflect") used by scripted backends."""
        ...

    def info(self) -> dict[str, Any]: ...
