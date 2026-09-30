from laya.agent.loop import parse_action
from laya.learning.skills import shape_and_slots, template_steps
from laya.tools.builtin import safe_eval
from laya.tools.registry import ToolError
import pytest


def test_safe_eval_and_rejects_code():
    assert safe_eval("17*23") == 391
    with pytest.raises(ToolError):
        safe_eval("__import__('os').system('x')")
    with pytest.raises(ToolError):
        safe_eval("9**999")


def test_parse_action_tolerates_noise():
    assert parse_action('sure! {"tool": "calculator", "args": {"expression": "1+1"}} done')["tool"] == "calculator"
    assert parse_action("not json") is None


def test_shape_and_templating():
    shape, slots = shape_and_slots("What is 17*23 and save it")
    assert shape == "what is <n>*<n> and save it" and slots == ["17", "23"]
    steps = [{"tool": "calculator", "args": {"expression": "17*23"}, "result": "391"},
             {"tool": "notes_add", "args": {"text": "17*23 = 391"}, "result": "saved"}]
    t = template_steps(steps, slots)
    assert t[0]["args"]["expression"] == "⟦s0⟧*⟦s1⟧"
    assert t[1]["args"]["text"] == "⟦s0⟧*⟦s1⟧ = ⟦r0⟧"


def test_agent_solves_with_tools(laya):
    r = laya.agent.run("What is 17*23?")
    assert r["status"] == "ok" and r["answer"] == "391" and r["via"] == "agent"


def test_multistep_and_approval_gating(laya):
    r = laya.agent.run("What is 6*7 and save it to notes")
    assert r["status"] == "ok" and [s["tool"] for s in r["steps"]] == ["calculator", "notes_add"]
    assert laya.store.q("SELECT text FROM notes")[0]["text"] == "6*7 = 42"
    # file_write is confirm-tier: without an approver it is denied
    laya.registry.set_tier("notes_add", "confirm")
    assert laya.agent.run("What is 2*2 and save it")["steps"][-1]["ok"] is False


def test_step_budget_and_loop_guard(laya):
    class Loopy:
        name = "loopy"
        def generate(self, *a, **k):
            return '{"tool": "get_time", "args": {}}'
        def info(self): return {}
    laya.agent.llm = Loopy()
    r = laya.agent.run("anything")
    assert r["status"] == "failed" and "loop" in r["error"]


def test_kill_switch(laya):
    laya.store.set_kv("killed", "1")
    assert laya.agent.run("What is 1+1?")["status"] == "blocked"


def test_workspace_sandbox(laya):
    with pytest.raises(ToolError):
        laya.registry.call("file_read", {"path": "../../etc/passwd"})


def test_final_after_failed_tool_is_not_success(laya):
    r = laya.agent.run("What is 1/0?")
    assert r["status"] == "failed" and "division by zero" in r["error"]
