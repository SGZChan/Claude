from __future__ import annotations

import json

from ..memory.store import Store


def export_jsonl(store: Store) -> str:
    """Training pairs from successful, not-rejected agent runs (for an optional LoRA fine-tune)."""
    lines = []
    for r in store.q("SELECT id FROM runs WHERE status='ok' AND feedback>=0 AND via='agent' ORDER BY id"):
        run = store.get_run(r["id"])
        assert run
        actions = [{"tool": s["tool"], "args": s["args"], "result": str(s.get("result", ""))[:500]} for s in run["steps"] if s.get("ok")]
        lines.append(json.dumps({"prompt": run["goal"], "actions": actions, "final": run["answer"]}))
    return "\n".join(lines)
