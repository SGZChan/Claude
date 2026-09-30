"""Wires settings, store, model, tools, skills and agent into one object."""
from __future__ import annotations

from .agent import Agent, Runner
from .config import Settings
from .features import FeatureManager
from .learning.skills import SkillLibrary
from .llm import load_llm
from .llm.base import LLM
from .memory.store import Store
from .tools import build_registry


class Laya:
    def __init__(self, settings: Settings | None = None, llm: LLM | None = None) -> None:
        self.settings = settings or Settings()
        self.settings.ensure_dirs()
        self.store = Store(self.settings.db_path)
        self.llm = llm or load_llm(self.settings)
        self.registry = build_registry(self.settings, self.store)
        self.skills = SkillLibrary(self.store, self.settings.promote_after)
        self.features = FeatureManager(self.store, self.registry)
        self.agent = Agent(self.settings, self.store, self.llm, self.registry, self.skills, self.features)
        self.runner = Runner(self.agent)
        self.features.bind(self)
