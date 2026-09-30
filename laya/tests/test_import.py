import json

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app
from laya.config import Settings
from laya.core import Laya
from laya.learning.export import export_jsonl
from laya.learning.importer import ImportErr, import_jsonl, parse_line


def line(prompt, *actions, **kw):
    return json.dumps({"prompt": prompt, "actions": list(actions), **kw})


def calc(expr, result="0"):
    return {"tool": "calculator", "args": {"expression": expr}, "result": result}


@pytest.fixture
def fresh(tmp_path_factory):
    return Laya(Settings(data_dir=tmp_path_factory.mktemp("fresh"), backend="mock"))


def test_parse_line_validation():
    known = {"calculator", "notes_add"}
    assert parse_line({"prompt": " hi ", "actions": [{"tool": "calculator", "args": {"expression": "1+1"}}]}, known)[0] == "hi"
    bad = [
        ([], "not a JSON object"),
        ({"actions": [{"tool": "calculator"}]}, "missing 'prompt'"),
        ({"prompt": "x"}, "non-empty list"),
        ({"prompt": "x", "actions": [{"tool": "nope", "args": {}}]}, "unknown tool"),
        ({"prompt": "x", "actions": [{"tool": "calculator", "args": {"expression": {"a": 1}}}]}, "short string or number"),
        ({"prompt": "x", "actions": [{"tool": "calculator", "args": []}]}, "must look like"),
        ({"prompt": "x" * 501, "actions": [{"tool": "calculator", "args": {}}]}, "longer than"),
        ({"prompt": "x", "actions": [{"tool": "calculator", "args": {}}] * 9}, "more than"),
    ]
    for obj, msg in bad:
        with pytest.raises(ImportErr, match=msg):
            parse_line(obj, known)


def test_import_promotes_skill_after_distinct_examples(fresh):
    text = "\n".join(line(f"What is {a}*{b}?", calc(f"{a}*{b}", str(a * b)), final=str(a * b)) for a, b in [(2, 3), (4, 5), (6, 7)])
    res = import_jsonl(fresh, text)
    assert res["valid"] == 3 and res["votes"] == 3 and res["skills_promoted"] == ["what is <n>*<n>"]
    assert res["lessons"] == 3 and res["invalid"] == [] and res["duplicates"] == 0
    r = fresh.agent.run("What is 9*9?")
    assert r["via"] == "skill" and r["answer"] == "81"           # learned purely from the imported file


def test_import_is_idempotent_and_dedupes_within_file(fresh):
    one = line("What is 2*3?", calc("2*3", "6"))
    res = import_jsonl(fresh, "\n".join([one, one, one]))
    assert res["valid"] == 3 and res["votes"] == 1 and res["duplicates"] == 2
    assert fresh.skills.list() == []                              # identical copies are one example, not three votes
    assert import_jsonl(fresh, one)["duplicates"] == 1


def test_reports_bad_lines_without_aborting(fresh):
    text = "\n".join(["not json", line("ok goal", calc("1+1", "2")), json.dumps({"prompt": "x"}), "", json.dumps([1])])
    res = import_jsonl(fresh, "\ufeff" + text)                    # BOM tolerated
    assert res["lines"] == 4 and res["valid"] == 1
    assert [i["line"] for i in res["invalid"]] == [1, 3, 5]


def test_options_and_dry_run(fresh):
    t = line("What is 2*3?", calc("2*3", "6"))
    d = import_jsonl(fresh, t, dry_run=True)
    assert d["valid"] == 1 and d["votes"] == 0 and fresh.store.list_facts("lesson") == []
    only_skills = import_jsonl(fresh, t, add_lessons=False)
    assert only_skills["votes"] == 1 and only_skills["lessons"] == 0
    t2 = line("What is 4*5?", calc("4*5", "20"))
    only_lessons = import_jsonl(fresh, t2, learn_skills=False)
    assert only_lessons["votes"] == 0 and only_lessons["lessons"] == 1


def test_old_format_without_results(fresh):
    single = line("What is 2*3?", {"tool": "calculator", "args": {"expression": "2*3"}})
    multi = line("What is 2*3 and save it", {"tool": "calculator", "args": {"expression": "2*3"}}, {"tool": "notes_add", "args": {"text": "2*3 = 6"}})
    res = import_jsonl(fresh, single + "\n" + multi)
    assert res["valid"] == 1 and res["votes"] == 1
    assert res["skipped"][0]["line"] == 2 and "without recorded results" in res["skipped"][0]["reason"]


def test_roundtrip_export_then_import_multistep(laya, fresh):
    for a, b in [(2, 3), (4, 5), (6, 7)]:
        laya.agent.run(f"What is {a}*{b} and save it to notes")
    exported = export_jsonl(laya.store)
    first = json.loads(exported.splitlines()[0])
    assert first["actions"][0]["result"] and first["actions"][1]["tool"] == "notes_add"   # results are now exported
    res = import_jsonl(fresh, exported)
    assert res["skills_promoted"] == ["what is <n>*<n> and save it to notes"]
    r = fresh.agent.run("What is 9*9 and save it to notes")
    assert r["via"] == "skill" and r["steps"][1]["args"]["text"] == "9*9 = 81"        # result reference, not a baked-in 6/20/42


def test_limits(fresh):
    with pytest.raises(ImportErr, match="too many lines"):
        import_jsonl(fresh, "\n".join(["{}"] * 5001))


def test_api_and_feature_gate(laya):
    c = TestClient(create_app(laya))
    text = "\n".join(line(f"What is {a}+{a}?", calc(f"{a}+{a}", str(2 * a))) for a in (1, 2, 3))
    d = c.post("/api/learning/import", json={"jsonl": text, "dry_run": True}).json()
    assert d["valid"] == 3 and d["dry_run"] is True and c.get("/api/skills").json() == []
    r = c.post("/api/learning/import", json={"jsonl": text}).json()
    assert r["skills_promoted"] == ["what is <n>+<n>"] and len(c.get("/api/skills").json()) == 1
    assert c.post("/api/learning/import", json={"jsonl": ""}).status_code == 422
    assert c.post("/api/learning/import", json={"jsonl": "\n".join(["{}"] * 5001)}).status_code == 422
    c.patch("/api/features/training_import", json={"enabled": False})
    assert c.post("/api/learning/import", json={"jsonl": text}).status_code == 403


def test_cli_import(tmp_path, capsys, monkeypatch):
    from laya.cli import main
    f = tmp_path / "t.jsonl"
    f.write_text(line("What is 2*3?", calc("2*3", "6")), encoding="utf-8")
    monkeypatch.setenv("LAYA_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("LAYA_BACKEND", "mock")
    main(["import", str(f)])
    assert '"votes": 1' in capsys.readouterr().out
