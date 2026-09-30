"""Local llama.cpp backend (default: Qwen2.5-0.5B-Instruct, Q4_K_M GGUF)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any


class LlamaCppLLM:
    name = "llama.cpp"

    def __init__(self, model_path: Path, n_ctx: int = 2048, n_threads: int | None = None) -> None:
        from llama_cpp import Llama  # optional dependency

        self.model_path = Path(model_path)
        self._llm = Llama(model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads, verbose=False)
        self._lock = threading.Lock()  # llama.cpp contexts are not thread-safe
        self.last_tps = 0.0

    def generate(self, prompt: str, *, schema: dict[str, Any] | None = None, task: str = "act", max_tokens: int = 256) -> str:
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object", "schema": schema}
        with self._lock:
            t0 = time.time()
            out = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
                **kwargs,
            )
            dt = max(time.time() - t0, 1e-6)
        self.last_tps = out.get("usage", {}).get("completion_tokens", 0) / dt
        return out["choices"][0]["message"]["content"] or ""

    def info(self) -> dict[str, Any]:
        return {"backend": self.name, "model": self.model_path.name, "tokens_per_sec": round(self.last_tps, 1)}
