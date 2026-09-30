from __future__ import annotations

from ..config import Settings
from .base import LLM
from .mock import MockLLM


def load_llm(settings: Settings) -> LLM:
    """auto: use llama.cpp when the package and model file exist, else the mock backend."""
    if settings.backend in ("auto", "llamacpp") and settings.model_path.exists():
        try:
            from .llamacpp import LlamaCppLLM

            return LlamaCppLLM(settings.model_path)
        except ImportError:
            if settings.backend == "llamacpp":
                raise
    elif settings.backend == "llamacpp":
        raise FileNotFoundError(f"model not found: {settings.model_path} (run scripts/download_model.py)")
    return MockLLM()


__all__ = ["LLM", "MockLLM", "load_llm"]
