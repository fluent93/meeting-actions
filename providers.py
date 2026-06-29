# -*- coding: utf-8 -*-
"""LLM provider — Gemini adapter for meeting extraction."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import retryutil
import schema


class LLMProvider(ABC):
    @abstractmethod
    def extract(self, transcript: str) -> dict:
        raise NotImplementedError


def _validate(data: dict) -> dict:
    missing = [k for k in schema.REQUIRED_TOP_KEYS if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")
    return data


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise ImportError("pip install google-genai") from e
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def extract(self, transcript: str) -> dict:
        config = self._types.GenerateContentConfig(
            system_instruction=schema.build_system_prompt(),
            response_mime_type="application/json",
            temperature=0,
        )
        resp = retryutil.with_retry(
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=transcript,
                config=config,
            )
        )
        text = (resp.text or "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Non-JSON response:\n{text[:500]}") from e
        return _validate(data)


def get_provider(name: str, api_key: str, model: str | None = None) -> LLMProvider:
    if name.lower() == "gemini":
        return GeminiProvider(api_key, model or "gemini-2.5-flash")
    raise ValueError(f"Unknown provider: {name}")
