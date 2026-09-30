from __future__ import annotations

import argparse
import json

from .core import Laya


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="laya", description="Laya (System One AI)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one goal")
    r.add_argument("goal")
    r.add_argument("--yes", action="store_true", help="auto-approve confirm-tier tools")
    s = sub.add_parser("serve", help="start API + dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    p = sub.add_parser("practice", help="self-practice on synthetic tasks")
    p.add_argument("-n", type=int, default=9)
    i = sub.add_parser("import", help="import a training-data .jsonl file")
    i.add_argument("path")
    i.add_argument("--no-lessons", action="store_true", help="only learn skills, don't store lessons")
    i.add_argument("--dry-run", action="store_true", help="validate only")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        from .api.app import create_app

        uvicorn.run(create_app(run_scheduler=True), host=a.host, port=a.port)
        return
    laya = Laya()
    print(f"[laya] model: {laya.llm.info()['model']}")
    if a.cmd == "run":
        res = laya.agent.run(a.goal, approver=(lambda t, x: True) if a.yes else None, emit=lambda e: print("  ", e["type"], {k: v for k, v in e.items() if k not in ("type", "t")}))
        print(f"\n[{res['via']}] {res['status']}: {res['answer'] or res['error']}")
    elif a.cmd == "import":
        from pathlib import Path

        from .learning.importer import import_jsonl

        print(json.dumps(import_jsonl(laya, Path(a.path).read_text(encoding="utf-8-sig"), True, not a.no_lessons, a.dry_run), indent=2))
    else:
        from .learning.curriculum import practice

        print(json.dumps(practice(laya, a.n), indent=2))


if __name__ == "__main__":
    main()
