"""
Translate tool backend — FastAPI.

    /                    static UI from public/
    GET  /api/health     backend + engine status
    GET  /api/languages  language list from LibreTranslate
    POST /api/translate  { q, source, target } -> { translatedText, detected }
    POST /api/tts        { text, lang }        -> audio/wav rendered by Piper

The browser never talks to LibreTranslate directly: proxying here keeps the
API key server-side and sidesteps CORS.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import translation, tts
from .config import MAX_CHARS, PUBLIC_DIR, settings
from .errors import AppError, register_error_handlers
from .schemas import (
    ErrorResponse,
    HealthResponse,
    Language,
    TranslateRequest,
    TranslateResponse,
    TtsRequest,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("translate")

NO_STORE = {"Cache-Control": "no-store"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await translation.startup()

    voices = tts.available_voices()
    log.info("Translate tool  ->  http://%s:%s", settings.host, settings.port)
    log.info("LibreTranslate  ->  %s", settings.lt_url)
    log.info(
        "Piper voices    ->  %s",
        ", ".join(voices) if voices else "none installed (browser speech will be used)",
    )

    yield
    await translation.shutdown()


app = FastAPI(
    title="Translate tool",
    description="LibreTranslate for translation, Piper for text-to-speech.",
    version="2.0.0",
    lifespan=lifespan,
    responses={"4XX": {"model": ErrorResponse}, "5XX": {"model": ErrorResponse}},
)

register_error_handlers(app)


@app.get("/api/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health() -> JSONResponse:
    """Engine status plus which languages have a Piper voice installed."""
    body: dict = {"translation": "down", "languages": 0, "tts": tts.available_voices()}

    try:
        languages = await translation.get_languages()
        body["translation"] = "up"
        body["languages"] = len(languages)
    except AppError as exc:
        # Health always answers 200 — the payload is the diagnosis.
        body["error"] = exc.message

    return JSONResponse(body, headers=NO_STORE)


@app.get("/api/languages", response_model=list[Language])
async def languages() -> JSONResponse:
    return JSONResponse(await translation.get_languages(), headers=NO_STORE)


@app.post("/api/translate", response_model=TranslateResponse)
async def translate(payload: TranslateRequest) -> JSONResponse:
    text = payload.q.strip()
    if not text:
        raise AppError("Nothing to translate.")
    if len(text) > MAX_CHARS:
        raise AppError(
            f"Text is too long (max {MAX_CHARS} characters).",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if not payload.target:
        raise AppError("A target language is required.")
    if payload.source == payload.target:
        return JSONResponse({"translatedText": text, "detected": None}, headers=NO_STORE)

    result = await translation.translate(text, payload.source, payload.target)

    detected = result.get("detectedLanguage")  # only reported when source is "auto"
    return JSONResponse(
        {
            "translatedText": result.get("translatedText") or "",
            "detected": (
                {
                    "language": detected.get("language"),
                    "confidence": round(detected.get("confidence") or 0),
                }
                if detected
                else None
            ),
        },
        headers=NO_STORE,
    )


@app.post(
    "/api/tts",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "Rendered speech"}},
)
async def text_to_speech(payload: TtsRequest) -> Response:
    text = payload.text.strip()
    if not text:
        raise AppError("Nothing to speak.")
    if len(text) > MAX_CHARS:
        raise AppError(
            "Text is too long to read aloud.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    voice = tts.voice_for(payload.lang)
    if voice is None:
        # 501 is the client's cue to fall back to the browser's speech synthesis.
        raise AppError(
            f'No Piper voice installed for "{payload.lang}".',
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            hint="Run ./setup.sh or download a voice into voices/.",
        )

    wav = await tts.synthesize(text, voice)
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={**NO_STORE, "X-Piper-Voice": voice.name},
    )


@app.get("/api/{_path:path}", include_in_schema=False)
async def unknown_api(_path: str) -> JSONResponse:
    return JSONResponse({"error": "Unknown endpoint"}, status_code=404, headers=NO_STORE)


# Mounted last so it only catches what the API routes above didn't.
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")
