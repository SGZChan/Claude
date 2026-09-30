"""Developer helper (repo search, read-only git, test runner) and the code sandbox."""
from __future__ import annotations

import re
import shlex
import subprocess
import sys

from .helpers import Ctx, read_text
from .registry import CONFIRM, ToolError

RUNNABLE = {"pytest -q", "python -m pytest -q", "npm test", "npm run build", "npm run lint"}
RO_CMDS = {"ls", "cat", "head", "wc", "pwd", "date"}


def install(ctx: Ctx) -> None:
    reg, ws = ctx.reg, ctx.ws

    def git(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(ws), *args], capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise ToolError(f"git unavailable: {e}")
        if r.returncode:
            raise ToolError((r.stderr or "git failed").strip()[:200])
        return r.stdout.strip()[:2000] or "(nothing)"

    @reg.register("repo_search", "regex search across code files in the workspace (find function, grep code)", {"pattern": "regex"}, feature="dev_helper")
    def repo_search(pattern: str) -> str:
        try:
            rx = re.compile(str(pattern), re.I)
        except re.error as e:
            raise ToolError(f"bad regex: {e}")
        hits = []
        for p in ctx.text_files():
            for i, line in enumerate(read_text(p).splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{ctx.rel(p)}:{i}: {line.strip()[:100]}")
                    if len(hits) >= 12:
                        return "\n".join(hits)
        return "\n".join(hits) or "no matches"

    @reg.register("git_status", "git status of the workspace repo (read-only)", {}, feature="dev_helper")
    def git_status() -> str:
        return git("status", "--short", "--branch")

    @reg.register("git_log", "recent git commits of the workspace repo (read-only)", {"n": "how many"}, feature="dev_helper", optional=("n",))
    def git_log(n: str = "5") -> str:
        return git("log", "--oneline", f"-n{max(1, min(int(n), 30))}")

    @reg.register("git_diff", "diff summary of uncommitted changes (read-only)", {}, feature="dev_helper")
    def git_diff() -> str:
        return git("diff", "--stat")

    @reg.register("run_tests", "run an allow-listed test/build command in the workspace: pytest -q, npm test, npm run build", {"command": "one of the allowed commands"},
                  tier=CONFIRM, feature="dev_helper")
    def run_tests(command: str) -> str:
        cmd = " ".join(str(command).split())
        if cmd not in RUNNABLE:
            raise ToolError(f"command not allowed; choose one of: {', '.join(sorted(RUNNABLE))}")
        parts = shlex.split(cmd)
        if parts[0] == "python":
            parts[0] = sys.executable
        try:
            r = subprocess.run(parts, capture_output=True, text=True, timeout=120, cwd=ws)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise ToolError(str(e))
        out = (r.stdout + r.stderr).strip().splitlines()
        return f"exit={r.returncode}; " + " / ".join(out[-4:])[:600]

    @reg.register("python_sandbox", "run a short Python snippet (isolated, 5s limit), returns stdout", {"code": "python code"}, tier=CONFIRM, feature="code_sandbox")
    def python_sandbox(code: str) -> str:
        try:
            r = subprocess.run([sys.executable, "-I", "-c", str(code)], capture_output=True, text=True, timeout=5, cwd=ws)
        except subprocess.TimeoutExpired:
            raise ToolError("timed out")
        return (r.stdout + r.stderr)[:2000] or "(no output)"

    @reg.register("shell_readonly", "run an allow-listed read-only command: ls cat head wc pwd date", {"command": "e.g. ls -la"}, tier=CONFIRM, feature="code_sandbox")
    def shell_readonly(command: str) -> str:
        parts = shlex.split(str(command))
        if not parts or parts[0] not in RO_CMDS or any(x in {"|", ";", "&&", ">", "<"} for x in parts):
            raise ToolError("command not allowed")
        for a in parts[1:]:
            if not a.startswith("-"):
                ctx.in_ws(a)
        r = subprocess.run(parts, capture_output=True, text=True, timeout=5, cwd=ws)
        return (r.stdout + r.stderr)[:2000] or "(no output)"
