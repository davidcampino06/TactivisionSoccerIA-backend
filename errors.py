"""API errors with a stable machine-readable code.

The frontend shows every message in Spanish by translating ``code``; ``detail`` stays in English
for logs and API docs. Response body: {"detail": "...", "code": "...", ...extra}.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str, headers: dict[str, str] | None = None,
                 **extra: Any) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.extra = extra


class DomainError(ValueError):
    """Business-rule error raised by services; routers turn it into an AppError with its code."""

    def __init__(self, message: str, code: str = "INVALID_REQUEST") -> None:
        super().__init__(message)
        self.code = code


def domain_error(error: DomainError, status_code: int) -> AppError:
    """Turns a service error into an API error; "not found" always answers 404 (no data leaks)."""
    return AppError(404 if error.code == "NOT_FOUND" else status_code, error.code, str(error))


async def app_error_handler(_: Request, error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail, "code": error.code, **error.extra},
        headers=error.headers,
    )
