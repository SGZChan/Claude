from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from ..config import Settings
from ..learning.reflect import reflect
from ..learning.skills import SkillLibrary, render_args
from ..llm.base import LLM
from ..memory.store import Store
from ..tools.registry import CONFIRM, Registry, ToolError

Emit = Callable[[dict[str, Any]], None]
Approver = Callable[[str, dict[str, Any]], bool]

ACTION_SCHEMA = {
    "type": "object",
    "properties": {"tool": {"type": "string"}, "args": {"type": "object"}, "final": {"type": "string"}},
}

PROMPT = """You are Laya, a small helpful agent. Solve the GOAL using tools, then reply with a final answer.
TOOLS:
{tools}
{memory}RULES: reply with ONE JSON object only.
- To use a tool: {{"tool": "<name>", "args": {{...}}}}
- When done: {{"final": "<short answer>"}}
Use each tool at most once per distinct input. Do not repeat finished steps.
GOAL: {goal}
{history}"""


def parse_action(text: str) -> dict[str, Any] | None:
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and (isinstance(obj.get("final"), str) or isinstance(obj.get("tool"), str)):
            return obj
    return None


class Agent:
    def __init__(self, settings: Settings, store: Store, llm: LLM, registry: Registry, skills: SkillLibrary, features=None) -> None:
        self.settings, self.store, self.llm, self.registry, self.skills = settings, store, llm, registry, skills
        self.features = features

    def feat(self, fid: str) -> bool:
        return self.features.enabled(fid) if self.features else True

    # -- helpers ----------------------------------------------------------
    def killed(self) -> bool:
        return self.store.get_kv("killed") == "1"

    def _exec_tool(self, name: str, args: dict[str, Any], emit: Emit, approver: Approver | None) -> tuple[bool, str]:
        tool = self.registry.get(name)
        if tool is None:
            return False, f"unknown tool '{name}'"
        if reason := self.registry.why_unavailable(tool):
            return False, reason
        if tool.tier == CONFIRM:
            emit({"type": "approval_request", "tool": name, "args": args})
            if approver is None or not approver(name, args):
                emit({"type": "approval_denied", "tool": name})
                return False, "denied: user approval required"
        try:
            out = self.registry.call(name, args)
            self.store.record_tool(name, True)
            return True, out
        except ToolError as e:
            self.store.record_tool(name, False)
            return False, str(e)

    def _prompt(self, goal: str, steps: list[dict[str, Any]]) -> str:
        mem = self.store.search_facts(goal, k=3, kinds=("lesson", "correction", "note")) if self.feat("memory_recall") else []
        memory = ("LESSONS:\n" + "\n".join(f"- {m['text']}" for m in mem) + "\n") if mem else ""
        hist = "".join(
            f"STEP {i}: {s['tool']}({json.dumps(s['args'])})\n-> {s['result']}\n" for i, s in enumerate(steps, 1))
        return PROMPT.format(tools=self.registry.prompt_block(goal), memory=memory, goal=goal, history=hist)

    # -- main entry -------------------------------------------------------
    def run(self, goal: str, *, run_id: int | None = None, emit: Emit | None = None, approver: Approver | None = None,
            stop: threading.Event | None = None, learn: bool = True, source: str = "user") -> dict[str, Any]:
        rid = run_id or self.store.create_run(goal)
        events: list[dict[str, Any]] = []
        t0 = time.time()

        def _emit(ev: dict[str, Any]) -> None:
            ev = {**ev, "t": round(time.time() - t0, 3)}
            events.append(ev)
            self.store.update_run(rid, events=events)
            if emit:
                emit(ev)

        steps: list[dict[str, Any]] = []
        answer, status, via, error, skill_id = "", "failed", "agent", "", None
        _emit({"type": "start", "goal": goal, "source": source})

        if self.killed():
            status, via, error = "blocked", "none", "kill switch is on"
        else:
            fast = self._try_skill(goal, _emit, approver) if self.feat("system_one") else None
            if fast:
                steps, answer, skill_id = fast["steps"], fast["answer"], fast["skill_id"]
                status, via = ("ok", "skill") if fast["ok"] else ("failed", "agent")
                if not fast["ok"]:  # skill failed -> fall back to full reasoning
                    _emit({"type": "route", "via": "agent", "reason": "skill failed, falling back"})
                    steps = []
            if via == "agent" and status != "ok":
                answer, steps, status, error = self._reason(goal, _emit, approver, stop, t0)

        ok = status == "ok"
        _emit({"type": "final" if ok else "error", "answer": answer, "error": error, "status": status})
        latency = round(time.time() - t0, 3)
        self.store.update_run(rid, status=status, answer=answer, via=via, steps=steps, ended=time.time(),
                              latency=latency, error=error, skill_id=skill_id, shape=None)
        if learn and status != "blocked":
            self._learn(goal, steps, ok, via)
        return {"id": rid, "status": status, "answer": answer, "via": via, "steps": steps, "latency": latency,
                "error": error, "skill_id": skill_id}

    # -- System One: learned skills --------------------------------------
    def _try_skill(self, goal: str, emit: Emit, approver: Approver | None) -> dict[str, Any] | None:
        m = self.skills.match(goal)
        if not m:
            return None
        skill, slots = m
        emit({"type": "route", "via": "skill", "skill_id": skill["id"], "skill": skill["name"]})
        steps: list[dict[str, Any]] = []
        results: list[str] = []
        for ts in skill["steps"]:
            args = render_args(ts["args"], slots, results)
            emit({"type": "tool_call", "tool": ts["tool"], "args": args})
            ok, out = self._exec_tool(ts["tool"], args, emit, approver)
            emit({"type": "tool_result", "tool": ts["tool"], "ok": ok, "result": out})
            steps.append({"tool": ts["tool"], "args": args, "result": out, "ok": ok})
            results.append(out.strip())
            if not ok:
                self.skills.record_use(skill["id"], False)
                return {"ok": False, "steps": steps, "answer": "", "skill_id": skill["id"]}
        self.skills.record_use(skill["id"], True)
        return {"ok": True, "steps": steps, "answer": results[-1] if results else "", "skill_id": skill["id"]}

    # -- System Two: constrained ReAct loop -------------------------------
    def _reason(self, goal: str, emit: Emit, approver: Approver | None, stop: threading.Event | None, t0: float):
        emit({"type": "route", "via": "agent"})
        steps: list[dict[str, Any]] = []
        seen: set[str] = set()
        invalid = 0
        for _ in range(self.settings.max_steps):
            if stop is not None and stop.is_set():
                return "", steps, "stopped", "stopped by user"
            if self.killed():
                return "", steps, "blocked", "kill switch is on"
            if time.time() - t0 > self.settings.run_timeout:
                return "", steps, "failed", "time budget exhausted"
            raw = self.llm.generate(self._prompt(goal, steps), schema=ACTION_SCHEMA, task="act")
            act = parse_action(raw)
            if act is None:
                invalid += 1
                emit({"type": "invalid_output", "raw": raw[:200]})
                if invalid >= 3:
                    return "", steps, "failed", "model produced invalid output"
                continue
            if isinstance(act.get("final"), str) and not act.get("tool"):
                if steps and not steps[-1]["ok"]:  # gave up right after a failed tool call
                    return act["final"], steps, "failed", f"last tool call failed: {steps[-1]['result']}"
                return act["final"], steps, "ok", ""
            name, args = act["tool"], act.get("args") or {}
            sig = name + json.dumps(args, sort_keys=True)
            if sig in seen:
                return "", steps, "failed", "loop detected (repeated identical tool call)"
            seen.add(sig)
            emit({"type": "tool_call", "tool": name, "args": args})
            ok, out = self._exec_tool(name, args, emit, approver)
            emit({"type": "tool_result", "tool": name, "ok": ok, "result": out})
            steps.append({"tool": name, "args": args, "result": out, "ok": ok})
        return "", steps, "failed", "step budget exhausted"

    # -- learning ---------------------------------------------------------
    def _learn(self, goal: str, steps: list[dict[str, Any]], ok: bool, via: str) -> None:
        if via != "agent":
            return
        if ok and self.feat("system_one"):
            promoted = self.skills.record_success(goal, steps)
            if promoted:
                self.store.add_fact("lesson", f"Learned skill '{promoted['name']}'", score=1.0)
        if (steps or not ok) and self.feat("reflection"):
            reflect(self.llm, self.store, goal, steps, ok)
