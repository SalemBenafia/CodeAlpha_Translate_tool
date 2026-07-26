"""
Piper text-to-speech.

The Node version shelled out to `python -m piper` for every request. Here the
backend is already Python, so voices are loaded in-process and kept warm: no
process spawn and no model reload per request. Synthesis is CPU-bound, so it
runs in a worker thread to keep the event loop responsive.
"""

import asyncio
import io
import logging
import threading
import wave
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from piper import PiperVoice

from .config import VOICES, settings
from .errors import AppError

log = logging.getLogger("translate")


@dataclass(frozen=True)
class Voice:
    name: str
    model: Path


def voice_for(lang: str | None) -> Voice | None:
    """
    Resolve the voice model for a language code, e.g. "es" -> es_ES-davefx-medium.

    LibreTranslate returns regional codes for some languages ("zh-Hans"), so an
    exact miss falls back to the base code ("zh").
    """
    if not isinstance(lang, str) or not lang:
        return None

    name = VOICES.get(lang) or VOICES.get(lang.split("-")[0])
    if not name:
        return None

    model = settings.voices_dir / f"{name}.onnx"
    # Piper needs the sidecar config too; treat a half-downloaded voice as absent
    # so the client falls back to browser speech instead of hitting an error.
    if not (model.is_file() and model.with_suffix(".onnx.json").is_file()):
        return None

    return Voice(name=name, model=model)


def available_voices() -> list[str]:
    """Languages we can actually speak right now (model file present on disk)."""
    return [lang for lang in VOICES if voice_for(lang)]


# Loading a model takes a second or two, so cache it. Guarded by a lock because
# two concurrent requests for a cold language would otherwise both load it.
_loaded: OrderedDict[str, PiperVoice] = OrderedDict()
_load_lock = threading.Lock()


def _get_loaded(voice: Voice) -> PiperVoice:
    with _load_lock:
        cached = _loaded.get(voice.name)
        if cached is not None:
            _loaded.move_to_end(voice.name)
            return cached

    # Load outside the lock: a cold model must not block other languages.
    log.info("loading Piper voice %s", voice.name)
    loaded = PiperVoice.load(str(voice.model))

    with _load_lock:
        # Another thread may have won the race; prefer its instance so both
        # callers share one session.
        existing = _loaded.get(voice.name)
        if existing is not None:
            return existing

        _loaded[voice.name] = loaded
        while len(_loaded) > settings.max_loaded_voices:
            evicted, _ = _loaded.popitem(last=False)
            log.info("evicting Piper voice %s", evicted)

    return loaded


def _synthesize_wav(text: str, voice: Voice) -> bytes:
    """Render text to an in-memory WAV. Blocking — always call in a thread."""
    loaded = _get_loaded(voice)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        loaded.synthesize_wav(text, wav_file)

    data = buffer.getvalue()
    if len(data) < 64:
        raise AppError("Piper produced no audio", status_code=502)
    return data


async def synthesize(text: str, voice: Voice) -> bytes:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_synthesize_wav, text, voice),
            timeout=settings.piper_timeout,
        )
    except TimeoutError as exc:
        # The worker thread can't be cancelled — it finishes and is discarded.
        raise AppError("Speech synthesis timed out", status_code=504) from exc
    except AppError:
        raise
    except Exception as exc:
        log.exception("Piper synthesis failed for %s", voice.name)
        raise AppError(f"Could not run Piper: {exc}", status_code=502) from exc
