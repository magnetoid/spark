import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from spark.config import get_settings
from spark.db import create_all
from spark.web import oauth, public, webhooks
from spark.web.deps import LoginRequired, templates

log = logging.getLogger("spark")
CSRF_EXEMPT_PREFIXES = ("/e/u/", "/webhooks/")
SPA_BASE = get_settings().spa_base.rstrip("/")  # "" once the app owns "/"
# The React app bundles everything, so it needs no CDNs, no eval and no inline scripts.
SPA_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data: blob: https:; media-src 'self' blob: https:; font-src 'self' data:; "
           "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")

# ---- rate limiting (token bucket per client+bucket; in-process, good enough per web container) ----
RATE_LIMITS = {  # path prefix -> (methods, requests, per_seconds)
    "/l/": ({"GET"}, 120, 60), "/b/": ({"GET", "POST"}, 60, 60), "/e/": ({"GET", "POST"}, 120, 60),
    "/webhooks/": ({"POST"}, 600, 60), "/mcp": ({"GET", "POST", "DELETE"}, 240, 60),
    "/api/v1/auth/": ({"POST"}, 10, 60),
}
_buckets: dict[tuple[str, str], list] = {}
_clock = __import__("time").monotonic  # tests freeze this so refills don't depend on machine speed


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))


def rate_limited(request: Request) -> bool:
    path = request.url.path
    for prefix, (methods, limit, per) in RATE_LIMITS.items():
        if path.startswith(prefix) and request.method in methods:
            key = (_client_ip(request), prefix)
            now = _clock()
            tokens, last = _buckets.get(key, (float(limit), now))
            tokens = min(float(limit), tokens + (now - last) * (limit / per))
            if tokens < 1:
                _buckets[key] = [tokens, now]
                return True
            _buckets[key] = [tokens - 1, now]
            return False
    return False


async def _load_connectors() -> None:
    """Apply connector values saved in the UI (cached for 30 s per process)."""
    from spark.db import SessionLocal
    from spark.services import connectors

    try:
        async with SessionLocal() as db:
            await connectors.refresh(db)
    except Exception:  # a missing table before migrations must not take the site down
        log.warning("Could not load connector settings", exc_info=True)


async def csrf_guard(request: Request) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.url.path.startswith(CSRF_EXEMPT_PREFIXES):
        return
    from spark.web.deps import CSRF_KEY

    expected = request.session.get(CSRF_KEY)
    sent = request.headers.get("X-CSRF-Token")
    if not sent and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        sent = (await request.form()).get(CSRF_KEY)
    if not expected or sent != expected:
        raise HTTPException(403, "Invalid or missing CSRF token — reload the page and try again")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.media_dir.mkdir(parents=True, exist_ok=True)
    if not s.is_production or s.database_url.startswith("sqlite"):
        await create_all()
    from spark import mcp_server

    async with mcp_server.session_manager_run():
        yield


def _spa_index():
    """index.html of the built React app, or None when there is no build (tests, API-only)."""
    index = get_settings().spa_dir / "index.html"
    return index if index.is_file() else None


def _mount_spa(app: FastAPI) -> None:
    """Serve the React app: hashed assets forever, every other path gets index.html (client routing)."""
    from starlette.staticfiles import StaticFiles as _Static

    class HashedAssets(_Static):
        def file_response(self, *args, **kwargs):
            resp = super().file_response(*args, **kwargs)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp

    assets_prefix = f"{SPA_BASE}/assets"

    async def assets(path: str):
        d = get_settings().spa_dir / "assets"
        if not d.is_dir():
            raise HTTPException(404)
        return await HashedAssets(directory=d).get_response(path, {"type": "http", "method": "GET", "headers": []})

    async def index(path: str = ""):
        file = _spa_index()
        if file is None:
            raise HTTPException(404, "The app is not built on this server")
        root = get_settings().spa_dir.resolve()
        if path and "/" not in path.strip("/"):
            # a file at the root of the build (theme.js, favicon.svg, manifest), never outside it
            candidate = (root / path).resolve()
            if candidate.parent == root and candidate.is_file() and candidate.name != "index.html":
                return FileResponse(candidate, headers={"Cache-Control": "public, max-age=3600"})
        return FileResponse(file, headers={"Cache-Control": "no-cache"})

    app.add_api_route(assets_prefix + "/{path:path}", assets, methods=["GET"], include_in_schema=False)
    if SPA_BASE:
        app.add_api_route(SPA_BASE, index, methods=["GET"], include_in_schema=False)
        app.add_api_route(SPA_BASE + "/{path:path}", index, methods=["GET"], include_in_schema=False)
    else:  # after the cutover the SPA owns every path no other route claimed
        app.add_api_route("/{path:path}", index, methods=["GET"], include_in_schema=False)


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # CSRF on every state-changing request as an app-level dependency (not middleware, so the
    # form body stays available to the route): token from the X-CSRF-Token header (htmx/fetch
    # add it from <meta name="csrf">) or the `csrf` form field. One-click email unsubscribe is
    # exempt: mail clients POST it without a session.
    app = FastAPI(title="Spark", docs_url=None, redoc_url=None, lifespan=lifespan,
                  dependencies=[Depends(csrf_guard)])
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key,
        https_only=s.is_production and s.base_url.startswith("https"),
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )
    s.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=s.media_dir), name="media")
    for r in (public.router, oauth.router, webhooks.router):
        app.include_router(r)
    from spark import mcp_server
    from spark.api.app import api as json_api

    app.router.routes.append(mcp_server.route)  # MCP over Streamable HTTP; bearer-token auth, no CSRF
    app.mount("/api/v1", json_api)  # JSON API for the React app; its own CSRF/auth rules live in spark.api.deps

    @app.middleware("http")
    async def guard_and_headers(request: Request, call_next):
        if rate_limited(request):
            return JSONResponse({"detail": "Too many requests — slow down a little"}, 429,
                                headers={"Retry-After": "30"})
        if not request.url.path.startswith(("/static/", "/media/", "/healthz")):
            await _load_connectors()
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith("/b/"):  # bio pages may be embedded
            h.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.url.path.startswith("/b/"):  # the public bio page: embeddable, loads one Google font
            h.setdefault("Content-Security-Policy",
                         "default-src 'self'; img-src * data: blob:; media-src * blob:; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; "
                         "connect-src 'self'; frame-ancestors *")
        h.setdefault("Content-Security-Policy", SPA_CSP)
        return response

    @app.exception_handler(Exception)
    async def _server_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        if "text/html" in request.headers.get("accept", "") and not request.headers.get("HX-Request"):
            return templates.TemplateResponse(request, "error.html",
                                              {"code": 500, "message": "Something broke on our side. It's logged; try again in a moment."}, 500)
        return JSONResponse({"detail": "Internal server error"}, 500)

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        if request.headers.get("HX-Request"):
            return HTMLResponse("", 401, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", 303)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
            return RedirectResponse(exc.headers["Location"], 303)
        if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(request, "error.html",
                                              {"code": 404, "message": "Page not found"}, 404)
        return JSONResponse({"detail": exc.detail}, exc.status_code, headers=exc.headers)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def _legacy_app_prefix(request: Request, path: str = ""):
        """Bookmarks from the migration period, when the app lived under /app."""
        q = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"/{path}{q}", 308)

    _mount_spa(app)

    return app


app = create_app()
