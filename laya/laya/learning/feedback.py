from __future__ import annotations

from ..memory.store import Store
from .skills import SkillLibrary


def apply_feedback(store: Store, skills: SkillLibrary, run: dict, rating: int, correction: str = "") -> None:
    """rating: +1 / -1 / 0. Updates the run, the skill used (if any) and memory."""
    prev = run.get("feedback", 0)
    store.update_run(run["id"], feedback=rating)
    if rating < 0 and prev >= 0:
        if run.get("skill_id"):
            skills.rate(run["skill_id"], -1)
        else:
            skills.retract(run["goal"], run["steps"])
        store.add_fact("lesson", f"User rejected result for '{run['goal'][:60]}'", score=0.5)
    elif rating > 0 and prev <= 0 and run.get("skill_id"):
        skills.rate(run["skill_id"], 1)
    if correction.strip():
        store.add_fact("correction", f"For '{run['goal'][:60]}': {correction.strip()}", score=1.5)
