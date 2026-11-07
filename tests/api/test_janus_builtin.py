"""Janus as a built-in service: Spark finds it on its own (compose wiring), creates the agent user
and token, pushes Janus's configuration over its config API, and exposes Janus's own options in
Settings. No address, no key, no YAML for the person installing Spark."""

import json

import httpx
import pytest
import respx
import yaml
from sqlalchemy import select

from spark.config import get_settings
from spark.models import Brand, Role, User
from tests.api.conftest import API

J = "http://janus:8642"


@pytest.fixture
def managed(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "janus_managed", True)
    monkeypatch.setattr(s, "janus_base_url", J)
    monkeypatch.setattr(s, "janus_api_key", "compose-generated-key")
    monkeypatch.setattr(s, "anthropic_api_key", "sk-ant-test")
    from spark.services import agent

    monkeypatch.setattr(agent, "INLINE_FOLLOW", False)
    return s


# ---- the agent user ---------------------------------------------------------------------------
async def test_agent_user_is_created_once_and_reads_every_brand(db, brand, managed):
    from spark.services import access, janus_setup, tokens

    other = Brand(name="Other", slug="other")
    db.add(other)
    await db.commit()
    user, raw = await janus_setup.ensure_agent(db)
    user2, raw2 = await janus_setup.ensure_agent(db)
    assert user.id == user2.id and raw == raw2 and user.role == Role.agent
    assert len((await db.execute(select(User).where(User.role == Role.agent))).scalars().all()) == 1
    assert await access.roles_for(db, user) == {brand.id: "viewer", other.id: "viewer"}
    assert not access.can_edit("viewer")
    assert (await tokens.user_for_token(db, raw)).id == user.id


# ---- the configuration Spark pushes -------------------------------------------------------------
async def test_desired_config_wires_janus_to_spark(db, brand, managed, monkeypatch):
    from spark.services import janus_setup

    monkeypatch.setattr(managed, "base_url", "https://spark.example.com")
    monkeypatch.setattr(managed, "janus_soul", "You help a small studio sound like itself.")
    monkeypatch.setattr(managed, "janus_effort", "high")
    text = await janus_setup.desired_config(db)
    cfg = yaml.safe_load(text)
    assert cfg["model"]["provider"] == "anthropic" and cfg["model"]["default"] == managed.ai_model
    assert cfg["agent"]["reasoning_effort"] == "high" and "terminal" in cfg["agent"]["disabled_toolsets"]
    assert cfg["approvals"]["mode"] == "manual"
    assert cfg["platform_toolsets"]["api_server"] == ["spark"]
    mcp = cfg["mcp_servers"]["spark"]
    assert mcp["url"] == "https://spark.example.com/mcp" and mcp["headers"]["Authorization"].startswith("Bearer spk_")
    assert "create_post" not in mcp["tools"]["include"] and "list_posts" in mcp["tools"]["include"]
    assert cfg["personalities"]["spark"]["system_prompt"].startswith("You help a small studio") and cfg["display"]["personality"] == "spark"
    # the person's own YAML wins where it overlaps
    monkeypatch.setattr(managed, "janus_extra_yaml", "agent:\n  max_turns: 40\nskills:\n  external_dirs: [/data/janus/skills]\n")
    cfg = yaml.safe_load(await janus_setup.desired_config(db))
    assert cfg["agent"]["max_turns"] == 40 and cfg["agent"]["reasoning_effort"] == "high" and cfg["skills"]["external_dirs"] == ["/data/janus/skills"]


# ---- pushing it -----------------------------------------------------------------------------------------
@respx.mock
async def test_sync_pushes_once_until_something_changes(db, brand, managed, monkeypatch):
    from spark.services import janus_setup

    respx.get(f"{J}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    put = respx.put(f"{J}/v1/config").mock(return_value=httpx.Response(200, json={"applied": ["raw"], "warnings": [], "restarting": True, "drain_timeout_seconds": 30}))
    assert (await janus_setup.sync(db))["result"] == "pushed"
    body = json.loads(put.calls.last.request.content)
    assert body["restart"] is True and body["api_keys"] == {"ANTHROPIC_API_KEY": "sk-ant-test"} and "mcp_servers" in body["raw"]
    assert put.calls.last.request.headers["authorization"] == "Bearer compose-generated-key"
    assert (await janus_setup.sync(db))["result"] == "unchanged" and put.call_count == 1
    monkeypatch.setattr(managed, "janus_effort", "low")
    assert (await janus_setup.sync(db))["result"] == "pushed" and put.call_count == 2
    respx.get(f"{J}/health").mock(return_value=httpx.Response(503, json={"status": "starting"}))
    monkeypatch.setattr(managed, "janus_effort", "medium")
    assert (await janus_setup.sync(db))["result"] == "unreachable" and put.call_count == 2


# ---- settings ------------------------------------------------------------------------------------------------
@respx.mock
async def test_settings_show_options_not_wiring_when_built_in(api, db, brand, managed):
    respx.get(f"{J}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    respx.get(f"{J}/v1/config").mock(return_value=httpx.Response(200, json={"object": "janus.config", "version": "0.18.0"}))
    put = respx.put(f"{J}/v1/config").mock(return_value=httpx.Response(200, json={"applied": ["raw"], "warnings": [], "restarting": True}))
    r = await api.get(f"{API}/settings/connectors/janus")
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()["fields"]]
    assert "janus_base_url" not in names and "janus_api_key" not in names
    assert {"janus_model", "janus_effort", "janus_approvals", "janus_soul", "janus_extra_yaml"} <= set(names)
    assert r.json()["extra"]["janus"]["managed"] is True and r.json()["configured"] is True
    r = await api.put(f"{API}/settings/connectors/janus", json={"values": {"janus_effort": "high", "janus_soul": "Short and kind."}, "clear": []})
    assert r.status_code == 200, r.text
    assert put.called and "Short and kind." in json.loads(put.calls.last.request.content)["raw"]
    r = await api.post(f"{API}/settings/janus/update")  # restart; the service pulls the latest Janus on the way back up
    assert r.status_code == 200 and json.loads(put.calls.last.request.content) == {"restart": True}
    st = (await api.get(f"{API}/brands/{brand.id}/agent/status")).json()
    assert st["configured"] and st["healthy"] and st["managed"] is True and st["can_update"] is True
    # the agent user is not a teammate to invite or email
    assert all(m["email"] != "janus@spark.local" for m in (await api.get(f"{API}/team")).json())


async def test_unmanaged_install_keeps_the_wiring_fields(api, brand):
    r = await api.get(f"{API}/settings/connectors/janus")
    names = [f["name"] for f in r.json()["fields"]]
    assert "janus_base_url" in names and "janus_api_key" in names and r.json()["extra"]["janus"]["managed"] is False
