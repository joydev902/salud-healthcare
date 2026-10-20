"""Opaque keyset cursors: base64url(JSON) of the last row's sort key."""

import base64
import json
from typing import Any

from app.core.errors import AppError

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, expected_len: int) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        values = None
    if not isinstance(values, list) or len(values) != expected_len:
        raise AppError(400, "INVALID_CURSOR", "Pagination cursor is invalid or expired")
    return values
