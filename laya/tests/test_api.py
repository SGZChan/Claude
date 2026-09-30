import time

import pytest
from fastapi.testclient import TestClient

from laya.api.app import create_app


@pytest.fixture
def client(laya):
    return TestClient(create_app(laya))


def wait(client, rid, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_run_lifecycle_and_stream(client):
    rid = client.post("/api/runs", json={"goal": "What is 17*23?"}).json()["id"]
    r = wait(client, rid)
    assert r["status"] == "ok" and r["answer"] == "391"
    body = client.get(f"/api/runs/{rid}/stream").text
    assert '"type": "tool_call"' in body and "event: done" in body


def test_approval_flow(client, laya):
    laya.registry.set_tier("calculator", "confirm")
    rid = client.post("/api/runs", json={"goal": "What is 2+2?"}).json()["id"]
    for _ in range(100):
        if client.get(f"/api/runs/{rid}").json()["pending_approval"]:
            break
        time.sleep(0.05)
    assert client.post(f"/api/runs/{rid}/approve", json={"approve": True}).status_code == 200
    assert wait(client, rid)["answer"] == "4"


def test_metrics_skills_feedback_memory(client, laya):
    for a in (2, 3, 4):
        wait(client, client.post("/api/runs", json={"goal": f"What is {a}*{a}?"}).json()["id"])
    assert len(client.get("/api/skills").json()) == 1
    ov = client.get("/api/metrics/overview").json()
    assert ov["kpis"]["runs_total"] == 3 and ov["kpis"]["skills_learned"] == 1 and len(ov["daily"]) == 14
    rid = client.get("/api/runs").json()[0]["id"]
    assert client.post(f"/api/runs/{rid}/feedback", json={"rating": 1}).status_code == 200
    assert client.get("/api/memory", params={"kind": "lesson"}).json()
    sid = client.get("/api/skills").json()[0]["id"]
    assert client.patch(f"/api/skills/{sid}", json={"enabled": False}).json()["enabled"] == 0
    assert client.get("/api/learning/export.jsonl").status_code == 200


def test_kill_switch_and_validation(client):
    assert client.post("/api/runs", json={"goal": ""}).status_code == 422
    client.post("/api/system/kill", json={"on": True})
    assert client.post("/api/runs", json={"goal": "hi"}).status_code == 423
    assert client.get("/api/system").json()["killed"] is True
