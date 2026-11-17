"""Bounded offline hash chains; checkpoints must come from a trusted caller.

This module performs no I/O, identity authorization, signing or persistence.
Event and affected-object bytes are retained exactly, not JSON-normalized.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re


NAMESPACE = "pya-offline-audit-envelope-v1"
MAX_EVENTS = 1024
MAX_VALUE_BYTES = 16_384
MAX_CHAIN_BYTES = 1_048_576
MAX_OBJECTS = 32
MAX_DEPTH = 16
MAX_NODES = 2048
MAX_INTEGER_DIGITS = 128
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ChainError(ValueError):
    """Invalid, oversized or checkpoint-inconsistent audit data."""


@dataclass(frozen=True, slots=True)
class Entry:
    chain_id: str
    sequence: int
    previous_digest: str
    event: bytes
    affected_objects: tuple[tuple[str, bytes], ...]
    digest: str


def _identifier(value: str) -> None:
    if type(value) is not str or not value or len(value) > 256:
        raise ChainError("Expected a bounded nonempty identifier")
    try:
        if len(value.encode("utf-8")) > 256 or any(ord(c) < 32 for c in value):
            raise ChainError("Invalid identifier")
    except UnicodeError as exc:
        raise ChainError("Invalid identifier Unicode") from exc


def _digest(value: str) -> None:
    if type(value) is not str or not _DIGEST.fullmatch(value):
        raise ChainError("Expected a lowercase SHA-256 digest")


def _envelope_digest(value: dict) -> str:
    # Private Python envelope encoding, not an adopted cross-language standard.
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def empty_head(chain_id: str) -> str:
    """Return the versioned empty-chain digest, bound to an external chain ID."""
    _identifier(chain_id)
    return _envelope_digest({"namespace": NAMESPACE, "kind": "empty",
                             "chain_id": chain_id})


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChainError("Duplicate JSON key")
        result[key] = value
    return result


def _integer(text):
    if len(text.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise ChainError("Integer precision limit exceeded")
    return int(text)


def _reject_number(_):
    raise ChainError("Use integer JSON numbers or explicit decimal strings")


def _json_bytes(value: bytes) -> None:
    if type(value) is not bytes or not value or len(value) > MAX_VALUE_BYTES:
        raise ChainError("Expected bounded immutable JSON bytes")
    try:
        parsed = json.loads(value.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_int=_integer, parse_float=_reject_number,
                            parse_constant=_reject_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ChainError("Invalid or unsupported JSON bytes") from exc
    if type(parsed) is not dict:
        raise ChainError("An event or affected object must be a JSON object")
    pending = [(parsed, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ChainError("JSON structure limit exceeded")
        if type(item) is dict:
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise ChainError("Invalid JSON Unicode") from exc


def _entry_digest(entry: Entry) -> str:
    return _envelope_digest({
        "namespace": NAMESPACE, "kind": "event", "chain_id": entry.chain_id,
        "sequence": entry.sequence, "previous_digest": entry.previous_digest,
        "event_sha256": hashlib.sha256(entry.event).hexdigest(),
        "affected_objects": [[key, hashlib.sha256(value).hexdigest()]
                             for key, value in entry.affected_objects],
    })


def verify(entries: tuple[Entry, ...], *, chain_id: str,
           expected_head: str, expected_count: int) -> str:
    """Verify an entire snapshot against REQUIRED externally trusted values.

    Returns the verified head. Supplying a head/count recomputed from untrusted
    entries proves only internal consistency, never authenticity or authority.
    """
    _identifier(chain_id)
    _digest(expected_head)
    if type(expected_count) is not int or not 0 <= expected_count <= MAX_EVENTS:
        raise ChainError("Invalid expected count")
    if type(entries) is not tuple or len(entries) != expected_count:
        raise ChainError("Snapshot count differs from trusted checkpoint")
    previous = empty_head(chain_id)
    total_bytes = 0
    for sequence, entry in enumerate(entries, 1):
        if type(entry) is not Entry or type(entry.sequence) is not int:
            raise ChainError("Invalid entry type or sequence")
        _identifier(entry.chain_id)
        if entry.chain_id != chain_id or entry.sequence != sequence:
            raise ChainError("Wrong chain or out-of-order sequence")
        _digest(entry.previous_digest)
        _digest(entry.digest)
        if entry.previous_digest != previous:
            raise ChainError("Broken prior-digest binding")
        _json_bytes(entry.event)
        total_bytes += len(entry.event)
        if (type(entry.affected_objects) is not tuple
                or not 1 <= len(entry.affected_objects) <= MAX_OBJECTS):
            raise ChainError("Invalid affected-object snapshot")
        prior_key = None
        for pair in entry.affected_objects:
            if type(pair) is not tuple or len(pair) != 2:
                raise ChainError("Invalid affected-object pair")
            key, value = pair
            _identifier(key)
            if prior_key is not None and key <= prior_key:
                raise ChainError("Affected objects must have unique sorted IDs")
            prior_key = key
            _json_bytes(value)
            total_bytes += len(key.encode("utf-8")) + len(value)
        if total_bytes > MAX_CHAIN_BYTES:
            raise ChainError("Chain content limit exceeded")
        if _entry_digest(entry) != entry.digest:
            raise ChainError("Modified event or affected-object content")
        previous = entry.digest
    if previous != expected_head:
        raise ChainError("Head differs from trusted checkpoint")
    return previous


def append(entries: tuple[Entry, ...], *, chain_id: str, event: bytes,
           affected_objects: dict[str, bytes], expected_head: str,
           expected_count: int) -> tuple[Entry, ...]:
    """Verify the prior snapshot and return a new immutable snapshot.

    The caller must retain the new head/count through its separately trusted
    checkpoint mechanism. Returning bytes/hashes grants no decision authority.
    """
    verify(entries, chain_id=chain_id, expected_head=expected_head,
           expected_count=expected_count)
    if expected_count == MAX_EVENTS:
        raise ChainError("Event count limit exceeded")
    _json_bytes(event)
    if type(affected_objects) is not dict or not 1 <= len(affected_objects) <= MAX_OBJECTS:
        raise ChainError("Expected a bounded affected-object dictionary")
    for key in affected_objects:
        _identifier(key)
    objects = tuple(sorted(affected_objects.items()))
    for _, value in objects:
        _json_bytes(value)
    pending = Entry(chain_id, expected_count + 1, expected_head, event, objects, "")
    entry = Entry(pending.chain_id, pending.sequence, pending.previous_digest,
                  pending.event, pending.affected_objects, _entry_digest(pending))
    result = entries + (entry,)
    # Enforce aggregate bounds on the same path used to verify received data.
    verify(result, chain_id=chain_id, expected_head=entry.digest,
           expected_count=expected_count + 1)
    return result
