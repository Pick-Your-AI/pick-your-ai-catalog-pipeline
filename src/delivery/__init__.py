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


class DeliveryError(ValueError):
    """Untrusted data is never interpolated into a public error message."""


def _check(payload: object, definition: str) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "$ref": "#/$defs/" + definition})
    if not validator.is_valid(payload):
        raise DeliveryError("invalid synthetic change feed")


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
        state = {"stream_id": feed["stream_id"], "cursor": 0, "hashes": {}, "withheld_versions": [], "recovery_pending": False}
    _check(state, "state")
    if state["stream_id"] != feed["stream_id"]:
        raise DeliveryError("synthetic stream identity mismatch")
    cursor = state["cursor"]
    hashes = dict(state["hashes"])
    withheld = set(state["withheld_versions"])
    actions: list[dict] = []
    resync = False
    unique: dict[int, dict] = {}
    for event in feed["events"]:
        index = event["sequence"]
        digest = _fingerprint(event)
        if index in unique and _fingerprint(unique[index]) != digest:
            raise DeliveryError("conflicting synthetic event sequence")
        unique[index] = event
    for sequence in sorted(unique):
        event = unique[sequence]
        digest = _fingerprint(event)
        if sequence <= cursor:
            if hashes.get(str(sequence)) != digest:
                resync = True
                break
            continue
        if sequence != cursor + 1:
            resync = True
            break
        cursor = sequence
        hashes[str(sequence)] = digest
        versions = [_version_key(x) for x in event["affected_versions"]]
        if event["kind"] == "mandatory_withdrawal":
            withheld.update(versions)
        actions.append({"event_id": event["event_id"], "sequence": sequence,
                        "required_action": event["required_action"],
                        "affected_versions": versions,
                        "receipt_status": "synthetic_unverified"})
    return {"publication_eligible": False, "delivery_authorized": False,
            "block_all_access": resync or state["recovery_pending"], "requires_resync": resync,
            "proposed_receipts": actions,
            "state": {"stream_id": state["stream_id"], "cursor": cursor,
                      "hashes": hashes, "withheld_versions": sorted(withheld),
                      "recovery_pending": state["recovery_pending"]}}


def recover_from_snapshot(snapshot: dict, state: dict) -> dict:
    """Synthetic offline recovery of a *complete* withdrawal snapshot.

    Real recovery additionally needs independent authentication, full lineage and
    authorization checks. This function does not confer any such authority.
    """
    _check(snapshot, "snapshot")
    _check(state, "state")
    if snapshot["stream_id"] != state["stream_id"] or snapshot["cursor"] < state["cursor"]:
        raise DeliveryError("invalid synthetic snapshot position")
    return {"publication_eligible": False, "delivery_authorized": False,
            "block_all_access": True, "requires_external_acceptance": True,
            "state": {"stream_id": state["stream_id"], "cursor": snapshot["cursor"],
                      "hashes": {}, "withheld_versions": sorted(set(
                          _version_key(x) for x in snapshot["complete_withdrawals"])),
                      "recovery_pending": True}}
