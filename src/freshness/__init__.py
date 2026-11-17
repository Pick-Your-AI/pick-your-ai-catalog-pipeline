"""Offline synthetic freshness evaluation, not source-policy or release authority.

Only explicit, source-scoped proposed policies are accepted. This module never
fetches a source, changes saved build identity, grants rights or publishes data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator

_VERSION = "freshness-draft-0.1.0"
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_OBSERVATION_FIELDS = frozenset({
    "schema_version", "synthetic", "claim_id", "source_id", "claim_type",
    "captured_at", "checked_at", "effective_at", "published_at", "source_status",
    "observation_ref", "snapshot_ref",
})
_REQUIRED_OBSERVATION_FIELDS = frozenset({
    "schema_version", "synthetic", "claim_id", "source_id", "claim_type",
    "captured_at", "source_status", "observation_ref",
})
_SOURCE_STATUSES = frozenset({"available", "unavailable", "unknown"})
_EVENTS = frozenset({
    "source_corrected", "price_changed", "availability_changed",
    "offering_changed", "source_policy_changed", "rights_changed", "snapshot_created",
})
_URN = re.compile(r"^urn:pya:synthetic:[a-z0-9][a-z0-9:._-]+$")


class FreshnessError(ValueError):
    """Invalid or unsupported synthetic freshness input, fail-closed."""


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise FreshnessError(f"{field}: explicit UTC Z instant required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreshnessError(f"{field}: invalid calendar instant") from exc


def _as_of(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise FreshnessError("as_of: explicit UTC-aware datetime required")
    return value.astimezone(timezone.utc)


def _policy_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas/freshness-policy.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate(policy: Mapping[str, Any], observation: Mapping[str, Any], *,
              as_of: datetime, events: tuple[str, ...]) -> dict[str, datetime]:
    if not isinstance(policy, dict) or not isinstance(observation, dict):
        raise FreshnessError("policy and observation must be plain objects")
    violations = list(_policy_validator().iter_errors(policy))
    if violations:
        raise FreshnessError("invalid proposed synthetic policy: " +
                             "; ".join(sorted(error.message for error in violations)))
    if not (_REQUIRED_OBSERVATION_FIELDS <= observation.keys() <= _OBSERVATION_FIELDS):
        raise FreshnessError("observation: missing or extra keys")
    if observation["schema_version"] != _VERSION or observation["synthetic"] is not True:
        raise FreshnessError("observation must be explicitly draft and synthetic")
    if not all(isinstance(observation[k], str) and _URN.fullmatch(observation[k])
               for k in ("claim_id", "source_id", "observation_ref")):
        raise FreshnessError("observation: synthetic identities required")
    if "snapshot_ref" in observation and (not isinstance(observation["snapshot_ref"], str)
                                          or not _URN.fullmatch(observation["snapshot_ref"])):
        raise FreshnessError("snapshot_ref: synthetic identity required")
    if observation["source_id"] != policy["source_id"] or observation["claim_type"] != policy["claim_type"]:
        raise FreshnessError("observation: claim type and exact source must match policy")
    if not isinstance(observation["source_status"], str) or observation["source_status"] not in _SOURCE_STATUSES:
        raise FreshnessError("observation: invalid source status")
    if any(not isinstance(event, str) or event not in _EVENTS for event in events):
        raise FreshnessError("events: unknown event must be inspected, not ignored")
    dates = {key: _instant(observation[key], key)
             for key in ("captured_at", "checked_at", "effective_at", "published_at")
             if key in observation}
    if any(value > as_of for key, value in dates.items() if key != "effective_at"):
        raise FreshnessError("observation contains a future capture, check or publication")
    if "checked_at" in dates and dates["checked_at"] < dates["captured_at"]:
        raise FreshnessError("checked_at may not precede captured_at")
    return dates


def evaluate(policy: Mapping[str, Any], observation: Mapping[str, Any], *,
             as_of: datetime, events: tuple[str, ...] = ()) -> dict[str, Any]:
    """Describe an *offline*, synthetic next step; never certify truth or release.

    Pinned evidence has no age-based expiry. A changed snapshot never changes
    that rule; a rights event always puts every class on hold. Current-state
    outputs are qualified only as of the explicit last check, never as 'live'.
    """
    now = _as_of(as_of)
    if not isinstance(events, tuple):
        raise FreshnessError("events must be an immutable tuple")
    dates = _validate(policy, observation, as_of=now, events=events)
    if "rights_changed" in events or "source_policy_changed" in events:
        status, action = "rights_hold", "review_exact_material_use_before_any_action"
    elif any(event in policy["event_triggers"] for event in events):
        status, action = "event_review", "preserve_last_known_and_review_event"
    elif observation["source_status"] == "unavailable":
        status, action = "source_unavailable", "preserve_last_known_and_escalate"
    elif observation["source_status"] == "unknown":
        status, action = "source_unknown", "resolve_source_status_without_guessing"
    elif policy["mode"] == "pinned":
        status, action = "pinned", "retain_version_reference_no_age_expiry"
    elif "effective_at" in dates and dates["effective_at"] > now:
        status, action = "not_yet_effective", "hold_current_state_until_effective"
    elif "checked_at" not in dates:
        status, action = "unchecked", "check_only_if_rights_allow"
    elif "review_interval_seconds" not in policy:
        status, action = "as_of_only", "monitor_approved_event_triggers"
    elif now - dates["checked_at"] >= timedelta(seconds=policy["review_interval_seconds"]):
        status, action = "review_due", "recheck_only_if_rights_allow"
    else:
        status, action = "checked_as_of", "retain_as_of_disclosure_and_monitor"
    result = {
        "schema_version": _VERSION,
        "synthetic": True,
        "publication_eligible": False,
        "claim_id": observation["claim_id"],
        "source_id": observation["source_id"],
        "policy_id": policy["policy_id"],
        "claim_type": policy["claim_type"],
        "status": status,
        "next_action": action,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
    }
    for field in ("captured_at", "checked_at", "effective_at", "published_at", "observation_ref", "snapshot_ref"):
        if field in observation:
            result[field] = observation[field]
    return result
