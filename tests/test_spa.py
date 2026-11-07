"""Serving the React app from /app next to the Jinja UI, with a strict CSP for it."""

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
    for path in ("/app", "/app/", "/app/publishing", "/app/posts/12/edit?brand=acme"):
        r = await client.get(path)
        assert r.status_code == 200 and 'id=root' in r.text, path
        assert "no-cache" in r.headers.get("cache-control", ""), path
    r = await client.get("/app/assets/app-abc123.js")
    assert r.status_code == 200 and "spa" in r.text
    assert "immutable" in r.headers.get("cache-control", "")
    assert (await client.get("/app/assets/missing.js")).status_code == 404
    # files at the root of the build (theme.js, favicon.svg) are served, not swallowed by the fallback
    r = await client.get("/app/theme.js")
    assert r.status_code == 200 and "classList" in r.text and "javascript" in r.headers["content-type"]
    assert (await client.get("/app/../pyproject.toml")).status_code in (404, 200) and "[project]" not in (await client.get("/app/..%2Fpyproject.toml")).text


async def test_spa_gets_a_strict_csp_and_the_old_ui_keeps_its_cdns(client, tmp_path, monkeypatch):
    await _spa(tmp_path, monkeypatch)
    strict = (await client.get("/app")).headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in strict and "script-src 'self'" in strict and "'unsafe-eval'" not in strict
    legacy = (await client.get("/queue")).headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in legacy


async def test_app_is_404_without_a_build(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "spa_dir", tmp_path / "nowhere")
    assert (await client.get("/app")).status_code == 404
    assert (await client.get("/app/publishing")).status_code == 404
