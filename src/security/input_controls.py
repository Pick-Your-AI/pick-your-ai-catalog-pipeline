"""Bounded, exact JSON parsing for untrusted source bytes.

This is a data-only parser, NOT a source fetcher, URL validator, rights gate,
HTML sanitizer, archive handler, or production admission decision.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json


class UnsafeJSONError(ValueError):
    """Rejected untrusted JSON; no raw source content is included in errors."""


DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_NODES = 10_000
MAX_INTEGER_DIGITS = 64
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_EXPONENT = 308


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise UnsafeJSONError("Duplicate object key")
        obj[key] = value
    return obj


def _integer(token):
    if len(token.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise UnsafeJSONError("Integer precision limit exceeded")
    return int(token)


def _decimal(token):
    if len(token) > 96:
        raise UnsafeJSONError("Decimal token length exceeded")
    try:
        number = Decimal(token)
    except InvalidOperation:
        number = None
    # Raise outside handler to avoid retaining raw input in __context__.
    if number is None:
        raise UnsafeJSONError("Invalid decimal number")
    parts = number.as_tuple()
    if len(parts.digits) > MAX_DECIMAL_DIGITS or abs(parts.exponent) > MAX_DECIMAL_EXPONENT:
        raise UnsafeJSONError("Decimal precision or exponent limit exceeded")
    if not number.is_finite():
        raise UnsafeJSONError("Nonfinite decimal number")
    return number


def _non_json_constant(_token):
    raise UnsafeJSONError("Non-JSON numeric constant")


def _safe_text(value):
    if "\x00" in value:
        raise UnsafeJSONError("NUL is not permitted in source metadata")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        valid = False
    else:
        valid = True
    if not valid:
        raise UnsafeJSONError("Invalid Unicode scalar value")


def parse_untrusted_json(
    payload: bytes | str, *, max_bytes: int = DEFAULT_MAX_BYTES,
    max_depth: int = DEFAULT_MAX_DEPTH, max_nodes: int = DEFAULT_MAX_NODES
):
    """Parse bounded UTF-8 JSON with no execution or implicit float rounding.

    Reject malformed UTF-8, duplicate keys, non-JSON constants, oversized
    payloads/numbers, excessive structure and invalid string code points.
    Decimal values stay Decimal until explicitly normalized by a later stage.
    """
    for limit in (max_bytes, max_depth, max_nodes):
        if type(limit) is not int or limit < 1:
            raise ValueError("All parser limits must be positive integers")
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        try:
            raw = payload.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raw = None
        if raw is None:
            raise UnsafeJSONError("Payload contains invalid Unicode")
    else:
        raise UnsafeJSONError("Payload must be UTF-8 bytes or text")
    if len(raw) > max_bytes:
        raise UnsafeJSONError("Payload byte limit exceeded")
    malformed = False
    try:
        source_text = raw.decode("utf-8", errors="strict")
        parsed = json.loads(
            source_text, object_pairs_hook=_unique_pairs,
            parse_int=_integer, parse_float=_decimal,
            parse_constant=_non_json_constant,
        )
    except UnsafeJSONError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        malformed = True
    # Do not chain exceptions containing JSONDecodeError.doc or raw bytes.
    if malformed:
        raise UnsafeJSONError("Malformed UTF-8 or JSON input")

    stack = [(parsed, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise UnsafeJSONError("JSON node limit exceeded")
        if depth > max_depth:
            raise UnsafeJSONError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            for key, item in value.items():
                _safe_text(key)
                stack.append((item, depth + 1))
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            _safe_text(value)
    return parsed
