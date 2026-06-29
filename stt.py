# -*- coding: utf-8 -*-
"""STT — Gemini audio transcription (English meetings, MVP)."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import retryutil

_MIME = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".mp4": "video/mp4",
}

TRANSCRIBE_PROMPT = """This audio is a work meeting (English unless clearly otherwise).
Transcribe verbatim with speaker labels when possible:

- Prefix each line with [Speaker N] or [Name] if names are obvious from context.
- Do not summarize or add content.
- Mark unclear audio as (unclear) — do not guess.
- Output transcript text only, no commentary."""


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        raise NotImplementedError


class GeminiSTTProvider(STTProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise ImportError("pip install google-genai") from e
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def transcribe(self, audio_path: str) -> str:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(audio_path)
        ext = os.path.splitext(audio_path)[1].lower()
        mime = _MIME.get(ext)
        up_cfg = {"mime_type": mime} if mime else None
        myfile = retryutil.with_retry(
            lambda: self._client.files.upload(file=audio_path, config=up_cfg)
        )
        resp = retryutil.with_retry(
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=[TRANSCRIBE_PROMPT, myfile],
                config=self._types.GenerateContentConfig(temperature=0),
            )
        )
        return (resp.text or "").strip()


def get_stt(name: str, api_key: str, model: str | None = None) -> STTProvider:
    if name.lower() == "gemini":
        return GeminiSTTProvider(api_key, model or "gemini-2.5-flash")
    raise ValueError(f"Unknown STT engine: {name}")
