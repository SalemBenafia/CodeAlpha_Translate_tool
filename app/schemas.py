"""Request and response models. Field names match what public/app.js sends."""

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    q: str = Field(description="Text to translate")
    source: str = Field(default="auto", description="Source language code, or 'auto'")
    target: str = Field(description="Target language code")


class Detected(BaseModel):
    language: str
    confidence: int


class TranslateResponse(BaseModel):
    translatedText: str  # noqa: N815 — the client reads this key verbatim
    detected: Detected | None = None


class TtsRequest(BaseModel):
    text: str
    lang: str


class Language(BaseModel):
    code: str
    name: str


class HealthResponse(BaseModel):
    translation: str = Field(description="'up' or 'down'")
    languages: int
    tts: list[str] = Field(description="Language codes with an installed Piper voice")
    error: str | None = None


class ErrorResponse(BaseModel):
    error: str
    hint: str | None = None
