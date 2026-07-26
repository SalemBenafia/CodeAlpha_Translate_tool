"""
Error plumbing.

The UI reads `{ "error": "..." }` off every failed response, so all of FastAPI's
default `{ "detail": ... }` bodies are rewritten into that shape here. Keeping the
translation in one place is what lets public/app.js stay untouched.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("translate")


class AppError(Exception):
    """An error worth showing to the user verbatim."""

    def __init__(self, message: str, status_code: int = 400, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.hint = hint


class EngineError(AppError):
    """LibreTranslate is unreachable, slow, or unhappy — always a 502."""

    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_502_BAD_GATEWAY)


def error_response(message: str, status_code: int, hint: str | None = None) -> JSONResponse:
    body: dict[str, str] = {"error": message}
    if hint:
        body["hint"] = hint
    return JSONResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.message, exc.status_code, exc.hint)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(detail, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # A malformed body is a client bug, not something the user can act on —
        # report the first offending field rather than pydantic's full tree.
        first = exc.errors()[0] if exc.errors() else None
        field = ".".join(str(p) for p in first["loc"][1:]) if first else ""
        message = f"Invalid request: {field or 'malformed body'}"
        return error_response(message, status.HTTP_400_BAD_REQUEST)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("[error] %s %s", request.method, request.url.path)
        return error_response(str(exc) or "Unexpected server error", status.HTTP_502_BAD_GATEWAY)
