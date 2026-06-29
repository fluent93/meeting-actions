# -*- coding: utf-8 -*-
"""Retry transient LLM/STT errors (503/429)."""

import sys
import time

_TRANSIENT_CODES = {429, 500, 503}
_TRANSIENT_STRINGS = (
    "503", "UNAVAILABLE", "high demand",
    "429", "RESOURCE_EXHAUSTED", "rate limit",
    "500", "overloaded", "deadline", "timeout",
)


def is_transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code in _TRANSIENT_CODES:
        return True
    s = str(exc).lower()
    return any(t.lower() in s for t in _TRANSIENT_STRINGS)


def with_retry(fn, *, tries: int = 8, base: float = 2.0, max_delay: float = 45.0):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if not is_transient(e) or attempt == tries - 1:
                raise
            delay = min(base * (2 ** attempt), max_delay)
            print(
                f"[retry {attempt + 1}/{tries - 1}] transient error, wait {delay:.0f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
