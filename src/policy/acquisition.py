"""Synthetic acquisition rehearsal: no network, response data or storage authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re
from threading import RLock


class AcquisitionError(ValueError):
    """A fixed diagnostic; never includes submitted values."""


def _fail(code):
    raise AcquisitionError(code)


def _shape(value, keys):
    if type(value) is not dict or any(type(k) is not str for k in value):
        _fail("invalid_shape")
    if set(value) != set(keys.split()):
        _fail("invalid_shape")


def _text(value, pattern, limit=256):
    if type(value) is not str or len(value) > limit or re.fullmatch(pattern, value) is None:
        _fail("invalid_value")


def _identity(value):
    _text(value, r"urn:pya:synthetic:[a-z0-9][a-z0-9:._-]*")


def _time(value):
    _text(value, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,6})?Z", 27)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise AcquisitionError("invalid_time") from None


def _fields(value):
    if type(value) is not list or not 1 <= len(value) <= 32:
        _fail("invalid_fields")
    for field in value:
        _text(field, r"[a-z][a-z0-9_.-]*", 80)
    if len(set(value)) != len(value):
        _fail("invalid_fields")


def _integer(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        _fail("invalid_integer")


def _request(request):
    _shape(request, "schema_version synthetic id source_id material_id product_id locator fields data_category credential_mode")
    if type(request["synthetic"]) is not bool or request["synthetic"] is not True:
        _fail("synthetic_required")
    for key in ("id", "source_id", "material_id", "product_id"):
        _identity(request[key])
    for key, expected in (("schema_version", "synthetic-acquisition-request-0.1"),
                          ("data_category", "metadata"), ("credential_mode", "none")):
        if type(request[key]) is not str or request[key] != expected:
            _fail("unsupported_request")
    # No credentials, ports, query, fragment, escapes, dot segments or real hosts.
    _text(request["locator"], r"https://example\.invalid/[a-z0-9][a-z0-9/_-]*")
    _fields(request["fields"])


def _decision(decision):
    _shape(decision, "schema_version synthetic id revision source_id material_id product_id locator fields operation status conditions valid_from expires_at retention max_simulated_calls")
    if type(decision["synthetic"]) is not bool or decision["synthetic"] is not True:
        _fail("synthetic_required")
    if type(decision["schema_version"]) is not str or decision["schema_version"] != "synthetic-acquisition-decision-0.1":
        _fail("unsupported_decision")
    for key in ("id", "source_id", "material_id", "product_id"):
        _identity(decision[key])
    _integer(decision["revision"], 1_000_000)
    _integer(decision["max_simulated_calls"], 100)
    _text(decision["locator"], r"https://example\.invalid/[a-z0-9][a-z0-9/_-]*")
    _fields(decision["fields"])
    if type(decision["operation"]) is not str or decision["operation"] != "retrieve":
        _fail("unsupported_operation")
    if type(decision["status"]) is not str or decision["status"] not in {"permit", "deny", "unknown", "conditional", "revoked"}:
        _fail("invalid_status")
    conditions = decision["conditions"]
    if type(conditions) is not list or len(conditions) > 16:
        _fail("invalid_conditions")
    for condition in conditions:
        _text(condition, r"[a-z][a-z0-9_-]*", 80)
    start, end = _time(decision["valid_from"]), _time(decision["expires_at"])
    if start >= end:
        _fail("invalid_interval")
    retention = decision["retention"]
    _shape(retention, "storage access max_age_seconds")
    for key, expected in (("storage", "synthetic_memory"), ("access", "rehearsal_only")):
        if type(retention[key]) is not str or retention[key] != expected:
            _fail("unsupported_retention")
    _integer(retention["max_age_seconds"], 3600)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True).encode("ascii")).hexdigest()


def _capture(value):
    """Detach bounded exact primitives before waiting on shared recorder state."""
    remaining = 256

    def take(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 4:
            _fail("invalid_policy_envelope")
        kind = type(item)
        if item is None or kind is bool:
            return item
        if kind is str and len(item) <= 256:
            return item
        if kind is int and -1000000 <= item <= 1000000:
            return item
        if (kind is not dict and kind is not list) or len(item) > 32:
            _fail("invalid_policy_envelope")
        result = {} if kind is dict else []
        for index, entry in enumerate(item.items() if kind is dict else item):
            if index >= 32:
                _fail("invalid_policy_envelope")
            if kind is dict:
                key, child = entry
                if type(key) is not str or len(key) > 256:
                    _fail("invalid_policy_envelope")
                result[key] = take(child, depth + 1)
            else:
                result.append(take(entry, depth + 1))
        return result

    try:
        return take(value)
    except RuntimeError:  # A concurrently resized caller dictionary is invalid.
        pass
    raise AcquisitionError("invalid_policy_envelope") from None


def _receipt(status, reason):
    return {"schema_version": "synthetic-acquisition-receipt-0.1", "synthetic": True,
            "status": status, "reason": reason, "evidence_level": "synthetic_unverified",
            "retrieval_authorized": False, "retention_authorized": False,
            "rights_cleared": False, "publication_eligible": False}


def preflight(request, decision, *, now):
    """Validate a single proposed decision; a simulated permit is never real authority."""
    _request(request)
    current = _time(now)
    if decision is None:
        return _receipt("denied", "missing_decision")
    _decision(decision)
    if any(request[k] != decision[k] for k in ("source_id", "material_id", "product_id", "locator")):
        return _receipt("denied", "scope_mismatch")
    if not set(request["fields"]).issubset(decision["fields"]):
        return _receipt("denied", "field_mismatch")
    if decision["status"] != "permit" or decision["conditions"]:
        return _receipt("denied", "permission_not_unconditional")
    if not _time(decision["valid_from"]) <= current < _time(decision["expires_at"]):
        return _receipt("denied", "decision_inactive")
    result = _receipt("simulated_permit", "synthetic_scope_matched")
    result["retention"] = deepcopy(decision["retention"])
    return result


def queue_request(request, decision, *, now):
    """Return a detached synthetic queue envelope, or a denial without queue data."""
    result = preflight(request, decision, now=now)
    if result["status"] != "simulated_permit":
        return result
    return {"schema_version": "synthetic-acquisition-queue-0.1", "synthetic": True,
            "request": deepcopy(request), "decision_digest": _digest(decision),
            "request_digest": _digest(request)}


class SimulatedRecorder:
    """In-memory fake only; stores digests/counters, never response bytes or locators."""

    def __init__(self):
        self._seen = set()
        self._budgets = {}
        self._decisions = {}
        self._calls = 0
        self._lock = RLock()

    @property
    def calls(self):
        with self._lock:
            return self._calls


def dispatch_queued(queued, current_decision, recorder, *, now):
    """Recheck policy and queue bindings before recording a hypothetical call.

    No callback/transport is accepted. In-memory duplicate and quota checks are
    rehearsal state, not durable scheduling, authenticated custody or retention.
    """
    if type(recorder) is not SimulatedRecorder:
        _fail("simulated_recorder_required")
    queued, current_decision = _capture(queued), _capture(current_decision)
    _shape(queued, "schema_version synthetic request decision_digest request_digest")
    if type(queued["schema_version"]) is not str or queued["schema_version"] != "synthetic-acquisition-queue-0.1" or queued["synthetic"] is not True:
        _fail("invalid_queue")
    for key in ("decision_digest", "request_digest"):
        _text(queued[key], r"[a-f0-9]{64}", 64)
    result = preflight(queued["request"], current_decision, now=now)
    if _digest(queued["request"]) != queued["request_digest"]:
        return _receipt("cancelled", "request_changed")
    if current_decision is None or _digest(current_decision) != queued["decision_digest"]:
        return _receipt("cancelled", "decision_changed")
    if result["status"] != "simulated_permit":
        return _receipt("cancelled", result["reason"])
    request_id = queued["request"]["id"]
    budget_key = (current_decision["id"], current_decision["revision"])
    with recorder._lock:
        if request_id in recorder._seen:
            return _receipt("cancelled", "request_already_recorded")
        prior = recorder._decisions.get(budget_key)
        if prior is not None and prior != queued["decision_digest"]:
            return _receipt("cancelled", "decision_revision_conflict")
        if recorder._budgets.get(budget_key, 0) >= current_decision["max_simulated_calls"]:
            return _receipt("cancelled", "simulated_quota_exhausted")
        if recorder._calls >= 100:
            return _receipt("cancelled", "recorder_capacity_exhausted")
        recorder._seen.add(request_id)
        recorder._budgets[budget_key] = recorder._budgets.get(budget_key, 0) + 1
        recorder._decisions[budget_key] = queued["decision_digest"]
        recorder._calls += 1
    return _receipt("simulated_call_recorded", "synthetic_only")
