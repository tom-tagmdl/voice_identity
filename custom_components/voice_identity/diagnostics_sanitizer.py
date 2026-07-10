"""Sanitization helpers for safe diagnostics projection.

These helpers enforce allowlist-style projection behavior by removing
prohibited keys and unsafe free-text values from nested payloads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from re import compile as re_compile

_SAFE_KEY_PATTERN = re_compile(r"^[a-z0-9_]+$")
_SAFE_REASON_CODE_PATTERN = re_compile(r"^[a-z0-9_]+$")
_SAFE_TOKEN_PATTERN = re_compile(r"^[a-z0-9_.:-]+$")
_UNSAFE_TEXT_PATTERN = re_compile(
    r"traceback|exception|stack|embedding|vector|transcript|audio|secret|token|password|apikey|api_key|key=|[a-z]:\\|/",
    flags=0,
)

_PROHIBITED_KEY_SUBSTRINGS = (
    "audio",
    "embedding",
    "vector",
    "transcript",
    "payload",
    "path",
    "mime",
    "bytes",
    "token",
    "secret",
    "password",
    "key",
    "trace",
    "exception",
    "stack",
)


def normalize_reason_code(value: str | None) -> str:
    """Normalize one reason code to a safe machine-readable token."""
    if value is None:
        return "unknown_reason"
    candidate = str(value).strip().lower()
    if not candidate or _SAFE_REASON_CODE_PATTERN.fullmatch(candidate) is None:
        return "unknown_reason"
    return candidate


def sanitize_mapping(payload: Mapping[str, object]) -> dict[str, object]:
    """Sanitize a nested mapping into deterministic safe primitives."""
    sanitized: dict[str, object] = {}
    for key in sorted(payload):
        normalized_key = _normalize_key(key)
        if normalized_key is None:
            continue
        if _is_prohibited_key(normalized_key):
            continue
        value = sanitize_value(payload[key], key_hint=normalized_key)
        if value is _SKIP:
            continue
        sanitized[normalized_key] = value
    return sanitized


def sanitize_value(value: object, *, key_hint: str | None = None) -> object:
    """Sanitize one value recursively to safe, serializable content."""
    if isinstance(value, bool | int | float) or value is None:
        return value

    if isinstance(value, str):
        return _sanitize_text(value=value, key_hint=key_hint)

    if isinstance(value, Mapping):
        sanitized = sanitize_mapping({str(k): v for k, v in value.items()})
        return sanitized

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        sanitized_items: list[object] = []
        for item in value:
            sanitized_item = sanitize_value(item, key_hint=key_hint)
            if sanitized_item is _SKIP:
                continue
            sanitized_items.append(sanitized_item)
        return sanitized_items

    return _SKIP


def safe_token(value: str | None, fallback: str) -> str:
    """Return a safe token string for diagnostics metadata."""
    if value is None:
        return fallback
    candidate = value.strip().lower()
    if not candidate or _SAFE_TOKEN_PATTERN.fullmatch(candidate) is None:
        return fallback
    return candidate


def _sanitize_text(*, value: str, key_hint: str | None) -> object:
    lowered = value.strip().lower()
    if not lowered:
        return ""

    if key_hint and _is_prohibited_key(key_hint):
        return _SKIP

    if _UNSAFE_TEXT_PATTERN.search(lowered) is not None:
        return "redacted"

    if _SAFE_TOKEN_PATTERN.fullmatch(lowered) is not None:
        return lowered

    return "redacted"


def _normalize_key(key: str) -> str | None:
    candidate = str(key).strip().lower()
    if not candidate:
        return None
    if _SAFE_KEY_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate


def _is_prohibited_key(key: str) -> bool:
    return any(fragment in key for fragment in _PROHIBITED_KEY_SUBSTRINGS)


_SKIP = object()
