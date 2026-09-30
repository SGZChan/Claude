"""Plugin platform: drop a .py file with `register(reg, ctx)` into <data_dir>/plugins and enable the feature.

Plugins are ordinary Python and run with full privileges, so the feature is off by default and only ever
loads files from your own plugins folder. Tools a plugin registers are forced to the confirm tier.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .helpers import Ctx
from .registry import CONFIRM

EXAMPLE = '''"""Example Laya plugin. Copy, edit, and restart or toggle the feature to reload."""


def register(reg, ctx):
    @reg.register("hello_plugin", "say hello to someone (example plugin)", {"name": "who to greet"}, feature="plugins")
    def hello_plugin(name):
        return f"Hello, {name}! (from a plugin)"
'''


def plugin_dir(ctx: Ctx) -> Path:
    d = ctx.settings.data_dir / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_plugins(ctx: Ctx) -> list[dict]:
    """(Re)load every plugin. Returns [{file, ok, tools|error}]."""
    ctx.reg.unregister_feature("plugins")
    d = plugin_dir(ctx)
    if not any(d.glob("*.py")):
        (d / "hello_plugin.py").write_text(EXAMPLE)
    out = []
    for f in sorted(d.glob("*.py")):
        before = set(ctx.reg.tools)
        try:
            spec = importlib.util.spec_from_file_location(f"laya_plugin_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            mod.register(ctx.reg, ctx)
            added = sorted(set(ctx.reg.tools) - before)
            for n in added:  # plugin tools always need approval and belong to the plugins feature
                ctx.reg.tools[n].tier, ctx.reg.tools[n].feature = CONFIRM, "plugins"
            out.append({"file": f.name, "ok": True, "tools": added})
        except Exception as e:  # a broken plugin must not break Laya
            for n in set(ctx.reg.tools) - before:
                del ctx.reg.tools[n]
            out.append({"file": f.name, "ok": False, "error": f"{type(e).__name__}: {e}"})
    return out


def install(ctx: Ctx) -> None:
    ctx.reg.plugin_loader = lambda: load_plugins(ctx)  # type: ignore[attr-defined]
