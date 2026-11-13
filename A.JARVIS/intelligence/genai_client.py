"""Shared Gemini client construction with bounded network behavior."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_GEMINI_TIMEOUT_MS = 15_000
DEFAULT_GEMINI_RETRY_ATTEMPTS = 2
RETRYABLE_HTTP_STATUS_CODES = [408, 429, 500, 502, 503, 504]


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def build_gemini_http_options(
    *,
    types_module: Any = None,
    timeout_ms_override: int | None = None,
    retry_attempts_override: int | None = None,
) -> Any:
    """Build bounded SDK HTTP options, optionally for one deadline-bound call.

    SDK timeout values are milliseconds. Request-level overrides are validated
    separately so a caller can pass the remaining budget without being rounded
    back up to the ordinary 15-second default. An attempts value of one means
    one total attempt, with no SDK retry/backoff outside the caller's deadline.
    """
    if types_module is None:
        from google.genai import types as types_module

    timeout_ms = _bounded_env_int(
        "GEMINI_TIMEOUT_MS",
        DEFAULT_GEMINI_TIMEOUT_MS,
        5_000,
        15_000,
    )
    if timeout_ms_override is not None:
        if isinstance(timeout_ms_override, bool) or not isinstance(timeout_ms_override, int):
            raise ValueError("Gemini timeout override must be an integer number of milliseconds.")
        if not 100 <= timeout_ms_override <= 180_000:
            raise ValueError("Gemini timeout override must be between 100 and 180,000 milliseconds.")
        timeout_ms = timeout_ms_override

    attempts = _bounded_env_int(
        "GEMINI_RETRY_ATTEMPTS",
        DEFAULT_GEMINI_RETRY_ATTEMPTS,
        1,
        2,
    )
    if retry_attempts_override is not None:
        if isinstance(retry_attempts_override, bool) or not isinstance(retry_attempts_override, int):
            raise ValueError("Gemini retry override must be an integer.")
        if not 1 <= retry_attempts_override <= 5:
            raise ValueError("Gemini retry override must be between 1 and 5.")
        attempts = retry_attempts_override

    retry_options = types_module.HttpRetryOptions(
        attempts=attempts,
        initial_delay=0.5,
        max_delay=3.0,
        exp_base=2.0,
        jitter=0.25,
        http_status_codes=RETRYABLE_HTTP_STATUS_CODES,
    )
    return types_module.HttpOptions(timeout=timeout_ms, retry_options=retry_options)


def create_genai_client(
    api_key: str,
    *,
    genai_module: Any = None,
    types_module: Any = None,
) -> Any:
    """Create a Gemini client, lazily importing the SDK for local/test use."""
    if not isinstance(api_key, str) or not api_key.strip():
        return None
    if genai_module is None:
        from google import genai as genai_module
    return genai_module.Client(
        api_key=api_key.strip(),
        http_options=build_gemini_http_options(types_module=types_module),
    )
