"""Synthetic-only CP-11.04 change feed and deterministic consumer replay proposals.

This module does not authenticate a publisher, authorize delivery, send messages,
clear source rights, or update any production consumer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "catalog-change-feed.schema.json"
MAX_REPLAY_ITEMS = 10_000


class DeliveryError(ValueError):
    """Untrusted data is never interpolated into a public error message."""


def _check(payload: object, definition: str) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "$ref": "#/$defs/" + definition})
    if not validator.is_valid(payload):
        raise DeliveryError("invalid synthetic change feed")
    if definition == "feed":
        integers = (event["sequence"] for event in payload["events"])
    elif definition == "state":
        integers = (payload["cursor"], payload["highest_observed_sequence"])
    else:
        integers = (payload["cursor"],)
    if any(type(value) is not int for value in integers):
        raise DeliveryError("noncanonical synthetic sequence")


def _fingerprint(event: dict) -> str:
    raw = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _version_key(version: dict) -> str:
    return version["artifact_id"] + "@" + version["revision"]


def replay(feed: dict, state: dict | None = None) -> dict:
    """Propose ordered/idempotent actions; a missing event blocks all access.

    The returned receipts are *synthetic proposals*, never delivery acknowledgements.
    State is an in-memory fixture, not authenticated persistent custody.
    """
    _check(feed, "feed")
    if state is None:
        state = {"stream_id": feed["stream_id"], "cursor": 0, "highest_observed_sequence": 0,
                 "hashes": {}, "pending_hashes": {}, "withheld_versions": [], "recovery_pending": False}
    _check(state, "state")
    if state["stream_id"] != feed["stream_id"]:
        raise DeliveryError("synthetic stream identity mismatch")
    cursor = state["cursor"]
    if state["highest_observed_sequence"] < cursor:
        raise DeliveryError("invalid synthetic replay state")
    hashes = dict(state["hashes"])
    pending = dict(state["pending_hashes"])
    if any(int(seq) <= cursor or int(seq) > state["highest_observed_sequence"]
           or int(seq) > 1_000_000_000 for seq in pending):
        raise DeliveryError("invalid synthetic replay state")
    withheld = set(state["withheld_versions"])
    actions: list[dict] = []
    resync = False
    unique: dict[int, dict] = {}
    seen_ids: dict[str, int] = {}
    for event in feed["events"]:
        index = event["sequence"]
        digest = _fingerprint(event)
        if index in unique and _fingerprint(unique[index]) != digest:
            raise DeliveryError("conflicting synthetic event sequence")
        identity = event["event_id"]
        if identity in seen_ids and seen_ids[identity] != index:
            raise DeliveryError("conflicting synthetic event identity")
        seen_ids[identity] = index
        unique[index] = event
    highest_observed = max(state["highest_observed_sequence"], max(unique))

    def blocked_for_recovery() -> dict:
        return {"publication_eligible": False, "delivery_authorized": False,
                "block_all_access": True, "requires_resync": True,
                "proposed_receipts": [],
                "state": {"stream_id": state["stream_id"], "cursor": cursor,
                          "highest_observed_sequence": highest_observed,
                          "hashes": dict(hashes), "pending_hashes": dict(pending),
                          "withheld_versions": sorted(withheld), "recovery_pending": True}}

    for sequence, event in unique.items():
        digest = _fingerprint(event)
        key = str(sequence)
        if ((sequence <= cursor and hashes.get(key) != digest)
                or (key in pending and pending[key] != digest)):
            return blocked_for_recovery()
    for sequence, event in unique.items():
        if sequence > cursor:
            key = str(sequence)
            if key not in pending and len(pending) >= MAX_REPLAY_ITEMS:
                return blocked_for_recovery()
            pending.setdefault(key, _fingerprint(event))
    for sequence in sorted(unique):
        event = unique[sequence]
        digest = _fingerprint(event)
        if sequence <= cursor:
            continue
        if sequence != cursor + 1:
            resync = True
            break
        versions = [_version_key(x) for x in event["affected_versions"]]
        if len(hashes) >= MAX_REPLAY_ITEMS or (event["kind"] == "mandatory_withdrawal"
                and len(withheld.union(versions)) > MAX_REPLAY_ITEMS):
            resync = True
            break
        cursor = sequence
        hashes[str(sequence)] = digest
        pending.pop(str(sequence), None)
        if event["kind"] == "mandatory_withdrawal":
            withheld.update(versions)
        actions.append({"event_id": event["event_id"], "sequence": sequence,
                        "required_action": event["required_action"],
                        "affected_versions": versions,
                        "receipt_status": "synthetic_unverified"})
    return {"publication_eligible": False, "delivery_authorized": False,
            "block_all_access": resync or cursor < highest_observed or bool(pending) or state["recovery_pending"],
            "requires_resync": resync or cursor < highest_observed or bool(pending) or state["recovery_pending"],
            "proposed_receipts": actions,
            "state": {"stream_id": state["stream_id"], "cursor": cursor,
                      "highest_observed_sequence": highest_observed, "hashes": hashes,
                      "pending_hashes": pending, "withheld_versions": sorted(withheld),
                      "recovery_pending": state["recovery_pending"]}}


def recover_from_snapshot(snapshot: dict, state: dict) -> dict:
    """Synthetic offline recovery of a *complete* withdrawal snapshot.

    Real recovery additionally needs independent authentication, full lineage and
    authorization checks. This function does not confer any such authority.
    """
    _check(snapshot, "snapshot")
    _check(state, "state")
    if snapshot["stream_id"] != state["stream_id"] or snapshot["cursor"] < max(
            state["cursor"], state["highest_observed_sequence"]):
        raise DeliveryError("invalid synthetic snapshot position")
    snapshot_withheld = set(_version_key(x) for x in snapshot["complete_withdrawals"])
    if not set(state["withheld_versions"]).issubset(snapshot_withheld):
        raise DeliveryError("synthetic snapshot omits prior withdrawal")
    return {"publication_eligible": False, "delivery_authorized": False,
            "block_all_access": True, "requires_external_acceptance": True,
            "state": {"stream_id": state["stream_id"], "cursor": snapshot["cursor"],
                      "highest_observed_sequence": snapshot["cursor"], "hashes": {},
                      "pending_hashes": {}, "withheld_versions": sorted(snapshot_withheld),
                      "recovery_pending": True}}
