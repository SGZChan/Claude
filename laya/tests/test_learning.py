from laya.learning.curriculum import practice
from laya.learning.export import export_jsonl
from laya.learning.feedback import apply_feedback


def test_skill_promoted_after_three_successes_then_fast_path(laya):
    for a, b in [(3, 4), (5, 6), (7, 8)]:
        assert laya.agent.run(f"What is {a}*{b}?")["via"] == "agent"
    skills = laya.skills.list()
    assert len(skills) == 1 and skills[0]["shape"] == "what is <n>*<n>"
    calls = {"n": 0}
    orig = laya.llm.generate
    laya.llm.generate = lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), orig(*a, **k))[1]
    r = laya.agent.run("What is 12*12?")
    assert r["via"] == "skill" and r["answer"] == "144" and calls["n"] == 0  # no LLM call


def test_multi_step_skill_generalises(laya):
    for a, b in [(2, 3), (4, 5), (6, 7)]:
        laya.agent.run(f"What is {a}*{b} and save it to notes")
    r = laya.agent.run("What is 9*9 and save it to notes")
    assert r["via"] == "skill" and "9*9 = 81" in r["steps"][1]["args"]["text"]


def test_failed_runs_do_not_promote(laya):
    for _ in range(4):
        laya.agent.run("What is 1/0?")
    assert laya.skills.list() == []


def test_negative_feedback_disables_skill(laya):
    for a in (2, 3, 4):
        laya.agent.run(f"What is {a}+{a}?")
    for q in ("What is 5+5?", "What is 8+8?"):  # two rejections disable it
        r = laya.agent.run(q)
        assert r["via"] == "skill"
        apply_feedback(laya.store, laya.skills, laya.store.get_run(r["id"]), -1)
    assert laya.skills.list()[0]["enabled"] == 0
    assert laya.agent.run("What is 6+6?")["via"] == "agent"


def test_reflection_memory_and_export(laya):
    laya.agent.run("What is 2*8?")
    assert laya.store.list_facts("lesson")
    assert laya.store.search_facts("what is 3*9", kinds=("lesson",))
    assert "2*8" in export_jsonl(laya.store)


def test_practice_learns_skills(laya):
    res = practice(laya, n=14, seed=1)
    assert res["passed"] == 14 and res["new_skills"] >= 1 and res["via_skill"] >= 1
