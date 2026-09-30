from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("LAYA_DATA_DIR", "./laya_data")))
    backend: str = field(default_factory=lambda: _env("LAYA_BACKEND", "auto"))
    model_path: Path = field(default_factory=lambda: Path(_env("LAYA_MODEL_PATH", "./models/qwen2.5-0.5b-instruct-q4_k_m.gguf")))
    max_steps: int = field(default_factory=lambda: int(_env("LAYA_MAX_STEPS", "6")))
    run_timeout: float = field(default_factory=lambda: float(_env("LAYA_RUN_TIMEOUT", "90")))
    promote_after: int = field(default_factory=lambda: int(_env("LAYA_PROMOTE_AFTER", "3")))
    approval_timeout: float = 120.0
    web_allowlist: list[str] = field(
        default_factory=lambda: [h for h in _env("LAYA_WEB_ALLOWLIST", "en.wikipedia.org,docs.python.org").split(",") if h]
    )

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.model_path = Path(self.model_path)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "laya.db"

    @property
    def workspace(self) -> Path:
        return self.data_dir / "workspace"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
