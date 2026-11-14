"""Serving the React app at /, with a strict CSP; the public bio page keeps its own policy."""

from pathlib import Path

from spark.config import get_settings


async def _spa(tmp_path: Path, monkeypatch) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Spark</title><div id=root></div>")
    (dist / "assets" / "app-abc123.js").write_text("console.log('spa')")
    (dist / "theme.js").write_text("document.documentElement.classList.add('dark')")
    monkeypatch.setattr(get_settings(), "spa_dir", dist)
    return dist


async def test_app_routes_fall_back_to_index_html(client, tmp_path, monkeypatch):
    await _spa(tmp_path, monkeypatch)
    for path in (
        "/",
        "/publishing",
        "/posts/12/edit?brand=acme",
        "/login",
        "/settings?tab=connectors",
    ):
        r = await client.get(path)
        assert r.status_code == 200 and "id=root" in r.text, path
        assert "no-cache" in r.headers.get("cache-control", ""), path
    r = await client.get("/assets/app-abc123.js")
    assert (
        r.status_code == 200
        and "spa" in r.text
        and "immutable" in r.headers.get("cache-control", "")
    )
    assert (await client.get("/assets/missing.js")).status_code == 404
    r = await client.get("/theme.js")
    assert (
        r.status_code == 200 and "classList" in r.text and "javascript" in r.headers["content-type"]
    )
    assert "[project]" not in (await client.get("/..%2Fpyproject.toml")).text


async def test_old_app_prefix_redirects(client, tmp_path, monkeypatch):
    await _spa(tmp_path, monkeypatch)
    r = await client.get("/app/publishing?view=calendar")
    assert r.status_code == 308 and r.headers["location"] == "/publishing?view=calendar"
    assert (await client.get("/app")).headers["location"] == "/"


async def test_csp_is_strict_except_the_public_bio_page(client, tmp_path, monkeypatch):
    await _spa(tmp_path, monkeypatch)
    strict = (await client.get("/")).headers["content-security-policy"]
    assert "script-src 'self'" in strict and "'unsafe-eval'" not in strict and "cdn." not in strict
    bio = (await client.get("/b/nope")).headers["content-security-policy"]
    assert "fonts.googleapis.com" in bio and "frame-ancestors *" in bio


async def test_api_routes_win_over_the_fallback(client, tmp_path, monkeypatch):
    await _spa(tmp_path, monkeypatch)
    assert (
        (await client.get("/api/v1/session")).headers["content-type"].startswith("application/json")
    )
    assert (await client.get("/healthz")).json()["ok"] is True
    assert (await client.get("/api/v1/nope")).status_code == 404


async def test_fallback_is_404_without_a_build(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "spa_dir", tmp_path / "nowhere")
    assert (await client.get("/publishing")).status_code == 404
