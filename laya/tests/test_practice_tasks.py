import random

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app
from laya.learning import tasks as T
from laya.learning.curriculum import practice


def mk(**kw):
    d = {"name": "t", "template": "Convert {a} miles to km", "params": "a: int 1..50", "check_type": "expr", "check_value": "{a}*1.609344"}
    d.update(kw)
    return d


# ---------------------------------------------------------------- parsing & validation
def test_parse_params():
    p = T.parse_params("a: int 2..9\nx: float 0.5..1.5; op: choice + | - | *")
    assert p["a"] == {"type": "int", "min": 2.0, "max": 9.0}
    assert p["x"]["type"] == "float" and p["op"]["values"] == ["+", "-", "*"]
    assert T.parse_params("") == {}
    for bad in ("a int 1..2", "a: int 9..1", "a: choice", "a: word 1..2"):
        with pytest.raises(T.TaskError):
            T.parse_params(bad)


@pytest.mark.parametrize("change,msg", [
    ({"name": ""}, "name is required"),
    ({"template": ""}, "template is required"),
    ({"check_type": "magic"}, "check type"),
    ({"check_value": ""}, "needs a check value"),
    ({"template": "Convert {zzz} miles"}, "undefined placeholder"),
    ({"check_type": "regex", "check_value": "("}, "regular expression"),
    ({"check_value": "__import__('os')"}, "can't be evaluated"),
    ({"tolerance": 5}, "tolerance"),
])
def test_validate_rejects(change, msg):
    with pytest.raises(T.TaskError, match=msg):
        T.validate(mk(**change))


def test_draw_is_reproducible_and_in_range():
    p = T.parse_params("a: int 1..5\nc: choice x | y")
    a, b = T.draw(p, random.Random(3)), T.draw(p, random.Random(3))
    assert a == b and 1 <= a["a"] <= 5 and a["c"] in ("x", "y")
    assert T.fill("go {a} {missing}", {"a": 2}) == "go 2 {missing}"


# ---------------------------------------------------------------- checkers
def chk(t, ans, steps=(), status="ok", values=None, **kw):
    task = {"check_type": t, "check_value": kw.get("v", ""), "tolerance": kw.get("tol", 0.001)}
    return T.check(task, values or {}, ans, list(steps), status)[0]


def test_checkers():
    assert chk("succeeds", "anything") and not chk("succeeds", "x", status="failed")
    assert chk("equals", " Hello ", v="hello") and not chk("equals", "hello world", v="hello")
    assert chk("contains", "It has 3 words.", v="3 WORDS")
    assert chk("regex", "id-42", v=r"id-\d+") and not chk("regex", "nope", v=r"id-\d+")
    assert chk("tool", "x", steps=[{"tool": "date_diff", "ok": True}], v="date_diff")
    assert not chk("tool", "x", steps=[{"tool": "date_diff", "ok": False}], v="date_diff")
    assert chk("expr", "8.0467 km", v="5*1.609344", tol=0.001)           # within relative tolerance
    assert not chk("expr", "9 km", v="5*1.609344", tol=0.001)
    assert chk("expr", "It is 1,234", v="1234")                          # thousands separators
    assert chk("expr", "17*23 = 391", v="17*23", tol=0)                  # any number in the answer can match
    assert chk("expr", "x", v="{a}*2", values={"a": 3}) is False          # placeholder filled -> 6 not in answer


# ---------------------------------------------------------------- persistence
def test_crud(laya):
    tid = T.add_task(laya.store, mk())
    assert T.list_tasks(laya.store)[0]["pass_rate"] is None
    with pytest.raises(T.TaskError, match="already exists"):
        T.add_task(laya.store, mk())
    T.add_task(laya.store, mk(name="t2"))
    with pytest.raises(T.TaskError, match="already exists"):
        T.update_task(laya.store, tid, mk(name="t2"))
    T.update_task(laya.store, tid, mk(name="renamed"))
    assert T.list_tasks(laya.store)[0]["name"] == "renamed"
    with pytest.raises(T.TaskError, match="no such task"):
        T.update_task(laya.store, 999, mk(name="q"))


def test_export_import_roundtrip(laya):
    T.add_task(laya.store, mk(name="a"))
    T.add_task(laya.store, mk(name="b", check_type="succeeds", check_value="", params="", template="Generate a passphrase"))
    data = T.export_tasks(laya.store)
    res = T.import_tasks(laya.store, data + [{"name": "bad"}, "junk"])
    assert res["added"] == 0 and len(res["errors"]) == 4                # 2 duplicates + 2 invalid
    laya.store.x("DELETE FROM practice_tasks")
    assert T.import_tasks(laya.store, data)["added"] == 2


# ---------------------------------------------------------------- running practice
def test_practice_runs_custom_task_and_tracks_stats(laya):
    tid = T.add_task(laya.store, mk(name="km"))
    res = practice(laya, n=4, seed=1, task_id=tid)
    assert res["passed"] == 4 and res["by_task"] == {"km": {"runs": 4, "passed": 4}}
    row = T.list_tasks(laya.store)[0]
    assert (row["runs"], row["passes"], row["pass_rate"]) == (4, 4, 1.0)
    assert laya.skills.list()                                            # repeated success -> learned skill


def test_failing_task_records_reason(laya):
    tid = T.add_task(laya.store, mk(name="wrong", check_value="{a}*100"))   # impossible expectation
    res = practice(laya, n=2, seed=1, task_id=tid)
    assert res["passed"] == 0 and "expected about" in res["failures"][0]["detail"]
    assert "expected about" in T.list_tasks(laya.store)[0]["last_fail"]


def test_mixed_practice_uses_builtin_and_only_enabled_custom(laya):
    a = T.add_task(laya.store, mk(name="on"))
    b = T.add_task(laya.store, mk(name="off", enabled=False))
    res = practice(laya, n=30, seed=2)
    assert set(res["by_task"]) <= {"Built-in arithmetic", "on"} and "on" in res["by_task"]
    assert res["passed"] == 30
    laya.features.set_enabled("custom_practice", False)
    assert set(practice(laya, n=5, seed=2)["by_task"]) == {"Built-in arithmetic"}
    with pytest.raises(T.TaskError):
        practice(laya, n=1, task_id=a)


def test_starter_pack_tasks_all_pass(laya):
    assert T.add_starter_pack(laya.store) == len(T.STARTER_PACK)
    assert T.add_starter_pack(laya.store) == 0                             # idempotent
    for t in T.list_tasks(laya.store):
        res = practice(laya, n=4, seed=5, task_id=t["id"])
        assert res["passed"] == 4, (t["name"], res["failures"])


# ---------------------------------------------------------------- API
@pytest.fixture
def client(laya):
    return TestClient(create_app(laya))


def test_api_flow(client, laya):
    body = mk(name="km")
    assert client.post("/api/practice/tasks", json=body).status_code == 201
    r = client.post("/api/practice/tasks", json=body)
    assert r.status_code == 422 and "already exists" in r.json()["detail"]
    r = client.post("/api/practice/tasks", json=mk(name="x", template="Convert {q}"))
    assert r.status_code == 422 and "undefined placeholder" in r.json()["detail"]
    assert client.post("/api/practice/tasks", json=mk(name="y", check_type="bogus")).status_code == 422
    tid = client.get("/api/practice/tasks").json()[0]["id"]
    assert client.put(f"/api/practice/tasks/{tid}", json=mk(name="km2")).status_code == 200
    out = client.post(f"/api/practice/tasks/{tid}/run", json={"n": 3}).json()
    assert out["passed"] == 3 and out["by_task"]["km2"]["runs"] == 3
    assert client.get("/api/practice/tasks").json()[0]["pass_rate"] == 1.0
    assert client.patch(f"/api/practice/tasks/{tid}", json={"enabled": False}).status_code == 200
    assert client.get("/api/practice/tasks").json()[0]["enabled"] == 0
    assert client.get("/api/practice/export").json()[0]["name"] == "km2"
    assert client.post("/api/practice/starter").json()["added"] == len(T.STARTER_PACK)
    imp = client.post("/api/practice/import", json={"tasks": [mk(name="km2"), mk(name="fresh")]}).json()
    assert imp["added"] == 1 and len(imp["errors"]) == 1
    assert client.delete(f"/api/practice/tasks/{tid}").status_code == 204
    assert client.post("/api/practice/tasks/999/run", json={"n": 1}).status_code == 422


def test_api_gated_by_feature_and_kill_switch(client, laya):
    tid = client.post("/api/practice/tasks", json=mk()).json()["id"]
    client.post("/api/system/kill", json={"on": True})
    assert client.post(f"/api/practice/tasks/{tid}/run", json={"n": 1}).status_code == 423
    client.post("/api/system/kill", json={"on": False})
    client.patch("/api/features/custom_practice", json={"enabled": False})
    for method, url in [("get", "/api/practice/tasks"), ("post", "/api/practice/starter"), ("get", "/api/practice/export")]:
        assert getattr(client, method)(url).status_code == 403
    assert client.post("/api/learning/practice", json={"n": 2}).status_code == 200   # built-in practice still works
