"""One JSON error shape for the whole API: {"code": "...", "detail": "..."}."""

from __future__ import annotations

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str, headers: dict | None = None):
        super().__init__(status_code, detail, headers)
        self.code = code


def login_required() -> ApiError:
    return ApiError(401, "login_required", "Sign in to continue")


def forbidden(detail: str = "Your role does not allow this") -> ApiError:
    return ApiError(403, "forbidden", detail)


def not_found(what: str = "Not found") -> ApiError:
    return ApiError(404, "not_found", what)
