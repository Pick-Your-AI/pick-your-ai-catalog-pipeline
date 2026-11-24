"""Bounded, exact JSON parsing for untrusted source bytes.

This is a data-only parser, NOT a source fetcher, URL validator, rights gate,
HTML sanitizer, archive handler, or production admission decision.
"""
from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation
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
        number = Decimal(token, context=Context(traps=[InvalidOperation]))
    except InvalidOperation:
        number = None
    # Raise outside handler to avoid retaining raw input in __context__.
    if number is None:
        raise UnsafeJSONError("Invalid decimal number")
    parts = number.as_tuple()
    if not number.is_finite():
        raise UnsafeJSONError("Nonfinite decimal number")
    if len(parts.digits) > MAX_DECIMAL_DIGITS or abs(parts.exponent) > MAX_DECIMAL_EXPONENT:
        raise UnsafeJSONError("Decimal precision or exponent limit exceeded")
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


def _preflight_json_nodes(source_text: str, max_nodes: int, max_depth: int) -> None:
    """Count JSON value positions before json.loads allocates the parse tree.

    For valid JSON, each object colon introduces one child value and each
    array item introduces one child value. Ignore punctuation inside strings.
    Reject excessive container nesting before allocating a deep decoder tree.
    This is only a resource preflight: json.loads remains the syntax authority
    and the existing postparse depth, type, and text checks remain mandatory.
    """
    nodes = 1  # root value
    containers = []  # [opening delimiter, first array item seen]
    in_string = False
    escaped = False
    for char in source_text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            if containers and containers[-1][0] == "[" and not containers[-1][1]:
                containers[-1][1] = True
                nodes += 1
            in_string = True
        elif char not in " \t\r\n":
            if containers and containers[-1][0] == "[" and not containers[-1][1] and char != "]":
                containers[-1][1] = True
                nodes += 1
            if char in "[{":
                if len(containers) >= max_depth:
                    raise UnsafeJSONError("JSON nesting limit exceeded")
                containers.append([char, False])
            elif char in "]}":
                if containers:
                    containers.pop()
            elif char == "," and containers and containers[-1][0] == "[":
                nodes += 1
            elif char == ":" and containers and containers[-1][0] == "{":
                nodes += 1
        if nodes > max_nodes:
            raise UnsafeJSONError("JSON node limit exceeded")


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
    if type(payload) is bytes:
        raw = payload
    elif type(payload) is str:
        # One UTF-8 code point always occupies at least one output byte.
        if len(payload) > max_bytes:
            raise UnsafeJSONError("Payload byte limit exceeded")
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
        _preflight_json_nodes(source_text, max_nodes, max_depth)
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
            for key in value:
                _safe_text(key)
            if nodes + len(stack) + len(value) > max_nodes:
                raise UnsafeJSONError("JSON node limit exceeded")
            for item in value.values():
                stack.append((item, depth + 1))
        elif isinstance(value, list):
            if nodes + len(stack) + len(value) > max_nodes:
                raise UnsafeJSONError("JSON node limit exceeded")
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            _safe_text(value)
    return parsed
