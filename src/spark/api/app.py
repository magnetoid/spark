"""The JSON API as its own FastAPI app, mounted at /api/v1 by `spark.main`.

A mounted app has its own OpenAPI document (only API routes, so the generated TypeScript
types stay clean) and its own exception handlers, so every error is JSON. The parent's
middleware (session cookie, rate limits, security headers) still wraps it.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from spark.api.errors import ApiError
from spark.api.routes import (
    ai,
    audience,
    bio,
    brands,
    campaigns,
    channels,
    collab,
    events,
    ideas,
    inbox,
    insights,
    library,
    links,
    palette,
    planning,
    posts,
    queue,
    session,
    settings,
    today,
)

log = logging.getLogger("spark.api")

api = FastAPI(title="Spark API", version="1.0", docs_url="/docs", openapi_url="/openapi.json",
              redoc_url=None)
for r in (session.router, brands.router, posts.router, queue.router, ideas.router, library.router, ai.router, today.router,
          insights.router, campaigns.router, links.router, audience.router, bio.router, channels.router, settings.router,
          inbox.router, palette.router, events.router, collab.router, collab.public, planning.router):
    api.include_router(r)


@api.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return JSONResponse({"code": exc.code, "detail": exc.detail}, exc.status_code, headers=exc.headers)


@api.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    code = {401: "login_required", 403: "forbidden", 404: "not_found", 429: "rate_limited"}.get(exc.status_code, "error")
    return JSONResponse({"code": code, "detail": exc.detail}, exc.status_code, headers=exc.headers)


@api.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"code": "validation", "detail": "Some fields are invalid", "errors": exc.errors()}, 422)


@api.exception_handler(Exception)
async def _server_error(request: Request, exc: Exception):
    log.exception("API error on %s %s", request.method, request.url.path)
    return JSONResponse({"code": "server_error", "detail": "Something broke on our side; it is logged"}, 500)
