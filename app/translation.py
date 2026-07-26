"""
LibreTranslate client.

The browser never talks to LibreTranslate directly: proxying here keeps the API
key server-side and sidesteps CORS.
"""

import time
from typing import Any

import httpx

from .config import settings
from .errors import EngineError

# One connection pool for the process, opened and closed by the app lifespan.
_client: httpx.AsyncClient | None = None

_language_cache: tuple[float, list[dict[str, Any]]] | None = None


async def startup() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.lt_url,
        timeout=settings.lt_timeout,
        headers={"Accept": "application/json"},
    )


async def shutdown() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _request(path: str, *, method: str = "GET", body: dict | None = None) -> Any:
    """Call LibreTranslate, turning every failure into an actionable message."""
    if _client is None:  # pragma: no cover — lifespan always runs first
        raise EngineError("Translation client is not ready.")

    try:
        response = await _client.request(method, path, json=body)
    except httpx.TimeoutException as exc:
        raise EngineError("LibreTranslate timed out — is the engine running?") from exc
    except httpx.TransportError as exc:
        # A booting container accepts the connection then drops it, so any
        # transport-level failure gets the same actionable message.
        refused = isinstance(exc, httpx.ConnectError)
        raise EngineError(
            f"Cannot reach LibreTranslate at {settings.lt_url} — "
            + (
                "the engine is not running."
                if refused
                else "it is still starting up, or is not responding."
            )
        ) from exc

    try:
        parsed = response.json()
    except ValueError as exc:
        raise EngineError(
            f"LibreTranslate returned a non-JSON response (HTTP {response.status_code})"
        ) from exc

    if response.is_error:
        detail = parsed.get("error") if isinstance(parsed, dict) else None
        raise EngineError(detail or f"LibreTranslate error (HTTP {response.status_code})")

    return parsed


async def get_languages() -> list[dict[str, Any]]:
    """Language list, cached so every page load doesn't hit the engine."""
    global _language_cache

    if _language_cache is not None:
        cached_at, languages = _language_cache
        if time.monotonic() - cached_at < settings.language_cache_seconds:
            return languages

    languages = await _request("/languages")
    _language_cache = (time.monotonic(), languages)
    return languages


async def translate(text: str, source: str, target: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"q": text, "source": source, "target": target, "format": "text"}
    if settings.lt_api_key:
        payload["api_key"] = settings.lt_api_key

    return await _request("/translate", method="POST", body=payload)
