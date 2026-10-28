import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from spark.config import get_settings
from spark.db import create_all
from spark.web import accounts, auth, brands, ideas, marketing, posts, public, queue
from spark.web.deps import LoginRequired, templates

log = logging.getLogger("spark")
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.media_dir.mkdir(parents=True, exist_ok=True)
    if not s.is_production or s.database_url.startswith("sqlite"):
        await create_all()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(title="Spark", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key,
        https_only=s.is_production and s.base_url.startswith("https"),
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )
    s.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/media", StaticFiles(directory=s.media_dir), name="media")
    for r in (public.router, auth.router, brands.router, accounts.router, posts.router, queue.router,
              ideas.router, marketing.router):
        app.include_router(r)

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
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, exc.status_code, headers=exc.headers)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
