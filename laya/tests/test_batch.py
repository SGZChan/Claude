import json

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app
from laya.cli import main, read_text_file
from laya.learning import tasks as T

LINES = """
# comment line
Miles to km | Convert {a} miles to km | a: int 1..50 | expr | {a}*1.609344
Passphrase | Generate a passphrase | | tool | passphrase
Mixed math | What is {a}{op}{b}? | a: int 2..9; b: int 2..9; op: choice +,-,* | expr | {a}{op}{b} | 0

Just finishes | Generate a passphrase
"""


def test_parse_lines_format():
    fmt, items, errors = T.parse_batch(LINES)
    assert fmt == "lines" and errors == [] and [d["name"] for _, d in items] == ["Miles to km", "Passphrase", "Mixed math", "Just finishes"]
    assert items[0][0] == 3                                                     # line numbers are real file lines
    assert T.parse_params(items[2][1]["params"])["op"]["values"] == ["+", "-", "*"]   # comma-separated choices work


def test_other_formats():
    js = json.dumps([{"name": "a", "template": "Generate a passphrase"}, "junk"])
    fmt, items, errors = T.parse_batch(js)
    assert fmt == "json" and len(items) == 1 and errors[0]["line"] == 2
    jl = '{"name": "a", "template": "t"}\nnot json\n{"name": "b", "template": "t"}'
    fmt, items, errors = T.parse_batch(jl)
    assert fmt == "jsonl" and len(items) == 2 and errors == [{"line": 2, "error": "not valid JSON"}]
    csv_text = 'name,template,params,check_type,check_value\nkm,"Convert {a} miles to km","a: int 1..5",expr,{a}*1.609344\n'
    fmt, items, errors = T.parse_batch("\ufeff" + csv_text)                     # BOM tolerated
    assert fmt == "csv" and items[0][1]["params"] == "a: int 1..5" and errors == []
    fmt, items, _ = T.parse_batch(csv_text.replace(",", "\t").replace('"', ""))
    assert fmt == "csv" and items[0][1]["name"] == "km"                          # spreadsheet paste (tabs)
    for bad in ("", "   \n  ", "[not json"):
        with pytest.raises(T.TaskError):
            T.parse_batch(bad)
    _, items, errors = T.parse_batch("only one field\na | b | c | d | e | f | g")
    assert items == [] and "at least" in errors[0]["error"] and "too many" in errors[1]["error"]


def test_batch_add_reports_per_line(laya):
    text = LINES + "Bad one | Convert {zzz} | | succeeds\nMiles to km | dup | | succeeds\nNo check value | hi | | expr\n"
    dry = T.batch_add(laya.store, text, dry_run=True)
    assert dry["added"] == 4 and T.list_tasks(laya.store) == []                  # dry run writes nothing
    res = T.batch_add(laya.store, text)
    assert res["added"] == 4 and res["duplicates"] == 1 and res["error_count"] == 2 and res["total"] == 7
    assert {e["line"] for e in res["errors"]} == {8, 10}                          # the real line numbers in the text
    assert "undefined placeholder" in res["errors"][0]["error"] and "needs a check value" in res["errors"][1]["error"]
    again = T.batch_add(laya.store, text)
    assert again["added"] == 0 and again["duplicates"] == 5
    assert T.list_tasks(laya.store)[0]["check_type"] == "expr"


def test_batch_respects_task_limit(laya, monkeypatch):
    monkeypatch.setattr(T, "MAX_TASKS", 3)
    res = T.batch_add(laya.store, "\n".join(f"t{i} | Generate a passphrase" for i in range(6)))
    assert res["added"] == 3 and res["error_count"] == 3 and "limit" in res["errors"][0]["error"]


def test_batch_tasks_actually_run(laya):
    T.batch_add(laya.store, LINES)
    for t in T.list_tasks(laya.store):
        from laya.learning.curriculum import practice
        assert practice(laya, n=3, seed=1, task_id=t["id"])["passed"] == 3, t["name"]


@pytest.fixture
def client(laya):
    return TestClient(create_app(laya))


def test_batch_api(client):
    r = client.post("/api/practice/batch", json={"text": LINES, "dry_run": True}).json()
    assert r["added"] == 4 and r["dry_run"] is True and client.get("/api/practice/tasks").json() == []
    r = client.post("/api/practice/batch", json={"text": LINES}).json()
    assert r["added"] == 4 and len(client.get("/api/practice/tasks").json()) == 4
    assert client.post("/api/practice/batch", json={"text": "[oops"}).status_code == 422
    assert client.post("/api/practice/batch", json={"text": ""}).status_code == 422
    client.patch("/api/features/custom_practice", json={"enabled": False})
    assert client.post("/api/practice/batch", json={"text": LINES}).status_code == 403


def test_memory_batch_api(client, laya):
    text = "# my notes\nWifi is on the fridge\n\nDentist on Tuesday\nWifi is on the fridge\n" + "x" * 501
    r = client.post("/api/memory/batch", json={"text": text}).json()
    assert r["added"] == 2 and r["duplicates"] == 1 and r["errors"] == [{"line": 6, "error": "longer than 500 characters"}]
    assert {f["text"] for f in client.get("/api/memory", params={"kind": "note"}).json()} == {"Wifi is on the fridge", "Dentist on Tuesday"}
    assert client.post("/api/memory/batch", json={"text": "a", "kind": "bogus"}).status_code == 422
    assert client.post("/api/memory/batch", json={"text": "\n".join(str(i) for i in range(1001))}).status_code == 422


def test_training_import_accepts_json_array(laya):
    from laya.learning.importer import ImportErr, import_jsonl
    arr = json.dumps([{"prompt": f"What is {a}*{a}?", "actions": [{"tool": "calculator", "args": {"expression": f"{a}*{a}"}, "result": str(a * a)}]} for a in (2, 3, 4)])
    assert import_jsonl(laya, arr)["skills_promoted"] == ["what is <n>*<n>"]
    with pytest.raises(ImportErr, match="invalid JSON array"):
        import_jsonl(laya, "[broken")


def test_cli_reads_utf16_and_batch(tmp_path, capsys, monkeypatch):
    f = tmp_path / "t.txt"
    f.write_bytes(LINES.encode("utf-16"))                                       # what PowerShell '>' produces
    assert read_text_file(str(f)).count("|") > 5
    g = tmp_path / "u.jsonl"
    g.write_bytes(b"\xef\xbb\xbf" + b'{"prompt": "x", "actions": []}')
    assert read_text_file(str(g)).startswith("{")
    monkeypatch.setenv("LAYA_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("LAYA_BACKEND", "mock")
    main(["add-tasks", str(f)])
    assert '"added": 4' in capsys.readouterr().out


def test_many_sources_share_duplicate_detection(laya):
    a = "Passphrase | Generate a passphrase | | tool | passphrase\nOne | Generate a passphrase"
    b = "name,template,params,check_type,check_value\nPassphrase,dup,,succeeds,\nTwo,Generate a passphrase,,succeeds,"
    dry = T.batch_add_many(laya.store, [a, b], dry_run=True)
    real = T.batch_add_many(laya.store, [a, b])
    assert (dry["added"], dry["duplicates"]) == (real["added"], real["duplicates"]) == (3, 1)      # a check predicts the real run
    assert [r["format"] for r in real["results"]] == ["lines", "csv"] and len(T.list_tasks(laya.store)) == 3
    bad = T.batch_add_many(laya.store, ["[oops", "Solo | Generate a passphrase"])
    assert "invalid JSON" in bad["results"][0]["failed"] and bad["added"] == 1                    # one bad source doesn't stop the rest


def test_batch_api_texts(client):
    a, b = "T1 | Generate a passphrase", "T1 | Generate a passphrase\nT2 | Generate a passphrase"
    r = client.post("/api/practice/batch", json={"texts": [a, b], "dry_run": True}).json()
    assert r["added"] == 2 and r["duplicates"] == 1 and client.get("/api/practice/tasks").json() == []
    assert client.post("/api/practice/batch", json={"texts": [a, b]}).json()["added"] == 2
    assert client.post("/api/practice/batch", json={}).status_code == 422


def test_import_dry_run_counts_repeats_like_the_real_run(laya):
    import json as _j
    from laya.learning.importer import import_jsonl
    one = _j.dumps({"prompt": "What is 2*3?", "actions": [{"tool": "calculator", "args": {"expression": "2*3"}, "result": "6"}]})
    dry = import_jsonl(laya, "\n".join([one, one]), dry_run=True)
    real = import_jsonl(laya, "\n".join([one, one]))
    assert (dry["valid"], dry["duplicates"]) == (real["valid"], real["duplicates"]) == (2, 1)
