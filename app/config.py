"""
All the knobs in one place. Every value can be overridden with an env var (or a
`.env` file), so nothing here needs editing for the common setups.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

# Longest text accepted by /api/translate and /api/tts. Mirrors the maxlength
# on the textarea, so the client normally never hits it.
MAX_CHARS = 5000

# Language code -> Piper voice. Add a row after downloading a new voice:
#   .venv/bin/python -m piper.download_voices --download-dir voices <name>
# Full catalogue: https://huggingface.co/rhasspy/piper-voices
VOICES: dict[str, str] = {
    "en": "en_US-lessac-medium",
    "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "it": "it_IT-paola-medium",
    "pt": "pt_BR-faber-medium",
    "ru": "ru_RU-dmitri-medium",
    "ar": "ar_JO-kareem-medium",
    "hi": "hi_IN-pratham-medium",
    "zh": "zh_CN-huayan-medium",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=3000, alias="PORT")

    # Local engine by default (docker run -p 5000:5000 libretranslate/libretranslate).
    # For the hosted service use:
    #   LT_URL=https://libretranslate.com LT_API_KEY=your-key python -m app
    lt_url: str = Field(default="http://localhost:5000", alias="LT_URL")
    lt_api_key: str = Field(default="", alias="LT_API_KEY")
    lt_timeout_ms: int = Field(default=20_000, alias="LT_TIMEOUT_MS")

    voices_dir: Path = Field(default=BASE_DIR / "voices", alias="PIPER_VOICES_DIR")
    piper_timeout_ms: int = Field(default=60_000, alias="PIPER_TIMEOUT_MS")

    # Loaded voices are kept warm in RAM (~60 MB each) and evicted least-recently
    # -used, so switching languages all day doesn't grow without bound.
    max_loaded_voices: int = Field(default=3, ge=1, alias="PIPER_MAX_LOADED_VOICES")

    # How long the language list is reused before re-asking LibreTranslate.
    language_cache_seconds: int = Field(default=600, alias="LANGUAGE_CACHE_SECONDS")

    @property
    def lt_timeout(self) -> float:
        return self.lt_timeout_ms / 1000

    @property
    def piper_timeout(self) -> float:
        return self.piper_timeout_ms / 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
