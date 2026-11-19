"""Deterministic, offline source-scan assessment for synthetic fixtures only.

Not an acquisition scheduler, rights authority, publication gate, or durable store.
"""

from __future__ import annotations

import re
from typing import Any

_VERSION = "reconciliation-draft-0.1.0"
_URN = re.compile(r"^urn:pya:synthetic:[a-z0-9][a-z0-9:._-]+$")
_STATES = frozenset({"ok", "parse_error", "broken_link", "quota_paused", "transport_error"})
_SCAN_KEYS = frozenset({"schema_version", "synthetic", "source_id", "scan_id", "window_id", "mode", "root_cursor", "start_cursor", "pages", "attempts"})
_PAGE_KEYS = frozenset({"cursor", "next_cursor", "status", "record_ids"})
_MAX_PAGES = 256
_MAX_IDS_PER_PAGE = 1000
_MAX_ID_LENGTH = 256
_REPORT_KEYS = frozenset({
    "schema_version", "synthetic", "publication_eligible", "source_id", "scan_id",
    "window_id", "mode", "status", "window_complete", "full_coverage_claimed",
    "resume_cursor", "failure", "next_action", "pages_seen", "record_ids",
    "record_count", "prior_count_changed", "deletion_inferred",
    "withdrawal_inferred", "last_known_preserved",
})


class ReconciliationError(ValueError):
    """Unsupported or ambiguous scan data; no partial trust of malformed data."""


def _synthetic(value: Any, field: str) -> str:
    if type(value) is not str or len(value) > _MAX_ID_LENGTH or not _URN.fullmatch(value):
        raise ReconciliationError(f"{field}: synthetic URN required")
    return value


def _int(value: Any, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ReconciliationError(f"{field}: integer outside allowed range")
    return value


def _object(value: Any, keys: frozenset[str], field: str) -> None:
    # Reject subclasses before invoking any user-defined mapping/key methods.
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value)
            or value.keys() != keys):
        raise ReconciliationError(f"{field}: exact dictionary with required fields expected")


def _ids(value: Any, limit: int) -> None:
    if type(value) is not list or len(value) > limit:
        raise ReconciliationError("record_ids: bounded list required")
    for item in value:
        _synthetic(item, "record_id")
    if len(value) != len(set(value)):
        raise ReconciliationError("record_ids: duplicate identities")


def assess_scan(scan: dict[str, Any], *, retry_budget: int = 3,
                prior_complete_count: int | None = None) -> dict[str, Any]:
    """Classify a bounded synthetic scan without performing IO or inferring deletions.

    A successful terminal page proves only that the *fixture claims* an endpoint.
    The returned resume cursor is a proposal, not a persisted atomic checkpoint.
    """
    _int(retry_budget, "retry_budget", 0, 20)
    if prior_complete_count is not None:
        _int(prior_complete_count, "prior_complete_count", 0, 1_000_000)
    _object(scan, _SCAN_KEYS, "scan")
    if (type(scan["schema_version"]) is not str or scan["schema_version"] != _VERSION
            or scan["synthetic"] is not True):
        raise ReconciliationError("scan: only explicit synthetic draft fixtures allowed")
    for field in ("source_id", "scan_id", "window_id", "root_cursor", "start_cursor"):
        _synthetic(scan[field], field)
    if type(scan["mode"]) is not str or scan["mode"] not in ("full", "incremental"):
        raise ReconciliationError("mode: full or incremental required")
    if scan["mode"] == "full" and scan["start_cursor"] != scan["root_cursor"]:
        raise ReconciliationError("full scan must start at explicit root cursor")
    _int(scan["attempts"], "attempts", 0, 1_000_000)
    pages = scan["pages"]
    if type(pages) is not list or not 1 <= len(pages) <= _MAX_PAGES:
        raise ReconciliationError("pages: nonempty bounded list required")
    expected = scan["start_cursor"]
    seen_cursors: set[str] = set()
    record_ids: set[str] = set()
    failure: str | None = None
    completed = False
    for index, page in enumerate(pages):
        _object(page, _PAGE_KEYS, "page")
        cursor = _synthetic(page["cursor"], "cursor")
        if cursor != expected or cursor in seen_cursors:
            raise ReconciliationError("page: cursor gap, cycle, or unexpected order")
        seen_cursors.add(cursor)
        status = page["status"]
        if type(status) is not str or status not in _STATES:
            raise ReconciliationError("page: unknown source status")
        ids = page["record_ids"]
        _ids(ids, _MAX_IDS_PER_PAGE)
        if status != "ok":
            if ids or page["next_cursor"] is not None or index != len(pages) - 1:
                raise ReconciliationError("failed page cannot claim observations, progress, or later pages")
            failure = status
            break
        record_ids.update(ids)
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            if index != len(pages) - 1:
                raise ReconciliationError("terminal page cannot have successors")
            completed = True
            expected = None
        else:
            expected = _synthetic(next_cursor, "next_cursor")
            if expected in seen_cursors:
                raise ReconciliationError("page: cyclic next cursor")
    exhausted = failure is not None and scan["attempts"] >= retry_budget
    if failure == "quota_paused":
        next_action = "await_quota_reset_and_recheck_rights"
    elif exhausted:
        next_action = "escalate_failure_without_advancing_checkpoint"
    elif failure:
        next_action = "retry_from_failing_cursor_if_rights_allow"
    elif not completed:
        next_action = "resume_from_next_cursor_if_rights_allow"
    else:
        next_action = "retain_observations_for_independent_review"
    state = ("escalate" if exhausted and failure != "quota_paused"
             else "degraded" if failure else "complete" if completed else "partial")
    # Only a completed full scan may be compared with a prior count. Even there,
    # a difference is a review signal, never proof of a deletion or withdrawal.
    count_changed = (len(record_ids) != prior_complete_count
                     if completed and scan["mode"] == "full" and prior_complete_count is not None
                     else None)
    return {
        "schema_version": _VERSION, "synthetic": True, "publication_eligible": False,
        "source_id": scan["source_id"], "scan_id": scan["scan_id"],
        "window_id": scan["window_id"], "mode": scan["mode"],
        "status": state, "window_complete": completed,
        "full_coverage_claimed": completed and scan["mode"] == "full",
        "resume_cursor": expected, "failure": failure, "next_action": next_action,
        "pages_seen": len(pages), "record_ids": sorted(record_ids),
        "record_count": len(record_ids), "prior_count_changed": count_changed,
        "deletion_inferred": False, "withdrawal_inferred": False,
        "last_known_preserved": True,
    }


def _validate_report(report: Any, mode: str) -> None:
    """Check declared structure/consistency, not execution history or custody."""
    _object(report, _REPORT_KEYS, "comparison report")
    for field in ("schema_version", "mode", "status", "next_action"):
        if type(report[field]) is not str:
            raise ReconciliationError(f"{field}: exact string required")
    if report["schema_version"] != _VERSION or report["mode"] != mode:
        raise ReconciliationError("comparison: draft version and full/incremental roles required")
    for field, expected in (("synthetic", True), ("publication_eligible", False),
                            ("deletion_inferred", False), ("withdrawal_inferred", False),
                            ("last_known_preserved", True)):
        if report[field] is not expected:
            raise ReconciliationError(f"{field}: synthetic safety marker contradicted")
    for field in ("source_id", "scan_id", "window_id"):
        _synthetic(report[field], field)
    for field in ("window_complete", "full_coverage_claimed"):
        if type(report[field]) is not bool:
            raise ReconciliationError(f"{field}: exact boolean required")
    pages = _int(report["pages_seen"], "pages_seen", 1, _MAX_PAGES)
    count = _int(report["record_count"], "record_count", 0, pages * _MAX_IDS_PER_PAGE)
    _ids(report["record_ids"], pages * _MAX_IDS_PER_PAGE)
    if count != len(report["record_ids"]):
        raise ReconciliationError("record_count: inconsistent with record_ids")
    failure = report["failure"]
    if failure is not None and (type(failure) is not str or failure not in _STATES - {"ok"}):
        raise ReconciliationError("failure: unknown failure status")
    complete = report["window_complete"]
    if complete:
        status, action = "complete", "retain_observations_for_independent_review"
        if failure is not None or report["resume_cursor"] is not None:
            raise ReconciliationError("complete report cannot retain a failure or resume cursor")
    else:
        _synthetic(report["resume_cursor"], "resume_cursor")
        if failure is None:
            status, action = "partial", "resume_from_next_cursor_if_rights_allow"
        elif failure == "quota_paused":
            status, action = "degraded", "await_quota_reset_and_recheck_rights"
        elif report["status"] == "escalate":
            status, action = "escalate", "escalate_failure_without_advancing_checkpoint"
        else:
            status, action = "degraded", "retry_from_failing_cursor_if_rights_allow"
    if report["status"] != status or report["next_action"] != action:
        raise ReconciliationError("comparison: status/action contradict coverage or failure")
    if failure is not None and count > (pages - 1) * _MAX_IDS_PER_PAGE:
        raise ReconciliationError("failed page cannot contribute observations")
    if report["full_coverage_claimed"] != (complete and mode == "full"):
        raise ReconciliationError("full coverage must match complete full-scan scope")
    changed = report["prior_count_changed"]
    if changed is not None and (type(changed) is not bool or not complete or mode != "full"):
        raise ReconciliationError("prior count comparison requires a complete full scan")


def compare_window(full: dict[str, Any], incremental: dict[str, Any]) -> dict[str, Any]:
    """Compare validated synthetic reports, without authenticating their origin.

    Both reports must declare the exact same source and observation window.
    A match is only equality of declared observed IDs with complete fixture windows.
    """
    for report, mode in ((full, "full"), (incremental, "incremental")):
        _validate_report(report, mode)
    if full["source_id"] != incremental["source_id"] or full["window_id"] != incremental["window_id"]:
        raise ReconciliationError("comparison: exact source and observation window must match")
    if not full["window_complete"] or not incremental["window_complete"]:
        outcome = "insufficient_coverage"
    else:
        outcome = "matched" if set(full["record_ids"]) == set(incremental["record_ids"]) else "divergent"
    return {"synthetic": True, "publication_eligible": False, "outcome": outcome,
            "requires_review": outcome != "matched", "deletion_inferred": False}
