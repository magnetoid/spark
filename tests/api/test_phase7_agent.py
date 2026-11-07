"""Phase 7, the agent half: Spark drives a Janus run over HTTP, follows its events, turns the
proposal it returns into drafts the team reviews, and never schedules anything by itself."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from spark.config import get_settings
from spark.models import Brand, Post, PostStatus
from tests.api.conftest import API

JANUS = "http://janus.test:8642"


@pytest.fixture
def janus(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "janus_base_url", JANUS)
    monkeypatch.setattr(s, "janus_api_key", "k-test")
    monkeypatch.setattr(s, "janus_update_webhook", "https://coolify.test/api/v1/deploy?uuid=j")
    from spark.services import agent

    monkeypatch.setattr(agent, "INLINE_FOLLOW", False)
    return s


def _sse(*events: dict) -> str:
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events) + ": stream closed\n\n"


def _proposal(posts: list[dict], **extra) -> str:
    body = {"summary": "Two posts for next week", "posts": posts, **extra}
    return "Here is the plan.\n\n```spark-proposal\n" + json.dumps(body) + "\n```\n"


async def test_agent_status_and_runs_need_janus(api, brand):
    r = await api.get(f"{API}/brands/{brand.id}/agent/status")
    assert r.status_code == 200 and r.json()["configured"] is False
    r = await api.post(f"{API}/brands/{brand.id}/agent/runs", json={"kind": "ask", "prompt": "plan something"})
    assert r.status_code == 409 and r.json()["code"] == "janus_not_configured"


@respx.mock
async def test_ask_run_follows_events_and_applies_proposal_as_drafts(api, db, brand, janus):
    from spark.services import agent

    bid = brand.id
    await api.patch(f"{API}/brands/{bid}", json={"agent_config": {"never_say": ["cheap"], "keywords": ["design"]}})
    await api.post(f"{API}/brands/{bid}/pillars", json={"name": "Education", "target_share": 50})
    when = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    start = respx.post(f"{JANUS}/v1/runs").mock(return_value=httpx.Response(202, json={"run_id": "run_abc", "status": "started"}))
    respx.get(f"{JANUS}/v1/runs/run_abc/events").mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"}, text=_sse(
        {"event": "message.delta", "run_id": "run_abc", "timestamp": 1.0, "delta": "Here is "},
        {"event": "tool.started", "run_id": "run_abc", "timestamp": 1.1, "tool": "mcp_spark_list_channels", "preview": "{}"},
        {"event": "tool.completed", "run_id": "run_abc", "timestamp": 1.2, "tool": "mcp_spark_list_channels", "duration": 0.1, "error": False},
        {"event": "run.completed", "run_id": "run_abc", "timestamp": 2.0, "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
         "output": _proposal([
             {"content": "Three design lessons from last week", "channels": ["acme"], "when": when.isoformat(), "pillar": "Education"},
             {"content": "Behind the scenes of a brand sprint", "channels": ["acme"], "when": None},
         ])},
    )))

    r = await api.post(f"{API}/brands/{bid}/agent/runs", json={"kind": "ask", "prompt": "Plan two posts about design for next week"})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["status"] in ("queued", "running") and run["kind"] == "ask"
    sent = json.loads(start.calls.last.request.content)
    assert start.calls.last.request.headers["authorization"] == "Bearer k-test"
    assert start.calls.last.request.headers["x-janus-session-key"] == f"spark-brand-{bid}"
    assert "Never use these words" in sent["instructions"] and "Education" in sent["instructions"] and "acme" in sent["instructions"]
    assert "spark-proposal" in sent["instructions"] and "Plan two posts" in sent["input"]

    # the worker follows the stream to the end
    assert await agent.follow(db, run["id"]) == "completed"
    r = await api.get(f"{API}/brands/{bid}/agent/runs/{run['id']}")
    out = r.json()
    assert out["status"] == "completed" and out["proposal"]["summary"] == "Two posts for next week"
    assert [p["content"] for p in out["proposal"]["posts"]][0].startswith("Three design")
    assert out["proposal"]["posts"][0]["channel_ids"] and out["proposal"]["posts"][0]["pillar_id"]
    assert [e["event"] for e in out["events"]] == ["message.delta", "tool.started", "tool.completed", "run.completed"]
    assert out["output"].startswith("Here is the plan.")
    assert [x["id"] for x in (await api.get(f"{API}/brands/{bid}/agent/runs")).json()] == [run["id"]]

    # nothing was created until the team says so
    assert (await api.get(f"{API}/brands/{bid}/posts")).json()["items"] == []
    r = await api.post(f"{API}/brands/{bid}/agent/runs/{run['id']}/apply", json={})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    items = (await api.get(f"{API}/brands/{bid}/posts", params={"status": "draft"})).json()["items"]
    assert len(items) == 2 and all(p["source"] == "janus" and p["agent_run_id"] == run["id"] for p in items)
    first = next(p for p in items if p["content"].startswith("Three design"))
    assert first["proposed_for"] and first["pillar_id"]
    assert (await api.get(f"{API}/brands/{bid}/agent/runs/{run['id']}")).json()["applied_at"]
    # applying twice does not duplicate
    assert (await api.post(f"{API}/brands/{bid}/agent/runs/{run['id']}/apply", json={})).status_code == 409

    # the review tray lists the plan; scheduling it places each post at its proposed time
    plan = (await api.get(f"{API}/brands/{bid}/agent/plan")).json()
    assert [p["id"] for p in plan["posts"]] == sorted(p["id"] for p in items) or len(plan["posts"]) == 2
    r = await api.post(f"{API}/brands/{bid}/agent/plan/schedule", json={"post_ids": [first["id"]]})
    assert r.status_code == 200 and r.json()["scheduled"] == 1
    p = await db.get(Post, first["id"])
    await db.refresh(p)
    assert p.status == PostStatus.scheduled and abs((p.scheduled_at.replace(tzinfo=UTC) - when).total_seconds()) < 60
    # the activity log knows
    verbs = [a["verb"] for a in (await api.get(f"{API}/brands/{bid}/activity")).json()["items"]]
    assert "asked Spark" in verbs and "applied" in verbs


@respx.mock
async def test_shell_approvals_are_denied_and_failures_recorded(api, db, brand, janus):
    from spark.services import agent

    bid = brand.id
    respx.post(f"{JANUS}/v1/runs").mock(return_value=httpx.Response(202, json={"run_id": "run_x", "status": "started"}))
    deny = respx.post(f"{JANUS}/v1/runs/run_x/approval").mock(return_value=httpx.Response(200, json={"run_id": "run_x", "choice": "deny", "resolved": 1}))
    respx.get(f"{JANUS}/v1/runs/run_x/events").mock(return_value=httpx.Response(200, text=_sse(
        {"event": "approval.request", "run_id": "run_x", "timestamp": 1.0, "command": "rm -rf build", "choices": ["once", "session", "always", "deny"]},
        {"event": "run.failed", "run_id": "run_x", "timestamp": 2.0, "error": "model exploded"},
    )))
    r = await api.post(f"{API}/brands/{bid}/agent/runs", json={"kind": "ask", "prompt": "do something"})
    assert await agent.follow(db, r.json()["id"]) == "failed"
    assert deny.called and json.loads(deny.calls.last.request.content)["choice"] == "deny"
    out = (await api.get(f"{API}/brands/{bid}/agent/runs/{r.json()['id']}")).json()
    assert out["status"] == "failed" and "model exploded" in out["error"]
    assert (await api.post(f"{API}/brands/{bid}/agent/runs/{r.json()['id']}/apply", json={})).status_code == 409


@respx.mock
async def test_voice_learning_proposes_a_profile_the_owner_accepts(api, db, brand, janus):
    from spark.services import agent

    bid = brand.id
    respx.post(f"{JANUS}/v1/runs").mock(return_value=httpx.Response(202, json={"run_id": "run_v", "status": "started"}))
    profile = {"tone": "Warm, direct, a little playful", "audience": "Founders of small studios", "rules": "Short sentences. No jargon.",
               "examples": "We built it in a weekend. Here is what broke.", "summary": "Plain talk from practitioners"}
    respx.get(f"{JANUS}/v1/runs/run_v/events").mock(return_value=httpx.Response(200, text=_sse(
        {"event": "run.completed", "run_id": "run_v", "timestamp": 2.0, "output": _proposal([], voice_profile=profile)},
    )))
    r = await api.post(f"{API}/brands/{bid}/agent/runs", json={"kind": "voice"})
    assert r.status_code == 202
    assert await agent.follow(db, r.json()["id"]) == "completed"
    out = (await api.get(f"{API}/brands/{bid}/agent/runs/{r.json()['id']}")).json()
    assert out["proposal"]["voice_profile"]["tone"].startswith("Warm")
    r = await api.post(f"{API}/brands/{bid}/agent/runs/{r.json()['id']}/apply", json={})
    assert r.status_code == 200 and r.json()["voice_applied"] is True
    b = await db.get(Brand, bid)
    await db.refresh(b)
    assert b.voice_profile["summary"] == "Plain talk from practitioners" and b.voice_tone.startswith("Warm")


@respx.mock
async def test_weekly_plan_run_is_started_by_the_scheduler_once_per_week(api, db, brand, janus):
    from spark.services import agent

    bid = brand.id
    start = respx.post(f"{JANUS}/v1/runs").mock(return_value=httpx.Response(202, json={"run_id": "run_w", "status": "started"}))
    await api.patch(f"{API}/brands/{bid}", json={"agent_config": {"weekly_plan": {"enabled": True, "weekday": datetime.now(UTC).weekday(), "posts": 5}}})
    db.expire_all()  # the API wrote through its own session
    assert await agent.start_due_weekly_plans(db) == 1
    assert await agent.start_due_weekly_plans(db) == 0  # not twice in the same week
    sent = json.loads(start.calls.last.request.content)
    assert "5 posts" in sent["input"] or "5 posts" in sent["instructions"]
    runs = (await api.get(f"{API}/brands/{bid}/agent/runs")).json()
    assert runs[0]["kind"] == "weekly_plan"


@respx.mock
async def test_janus_connector_test_and_update(api, janus):
    respx.get(f"{JANUS}/health").mock(return_value=httpx.Response(200, json={"status": "ok", "platform": "janus-agent"}))
    respx.get(f"{JANUS}/v1/config").mock(return_value=httpx.Response(200, json={"object": "janus.config", "version": "0.18.0"}))
    r = await api.post(f"{API}/settings/connectors/janus/test")
    assert r.status_code == 200 and "0.18.0" in r.json()["message"]
    hook = respx.get("https://coolify.test/api/v1/deploy").mock(return_value=httpx.Response(200, json={"message": "queued"}))
    r = await api.post(f"{API}/settings/janus/update")
    assert r.status_code == 200 and hook.called
    s = (await api.get(f"{API}/brands/1/agent/status")).json()
    assert s["configured"] is True and s["healthy"] is True and s["version"] == "0.18.0"
