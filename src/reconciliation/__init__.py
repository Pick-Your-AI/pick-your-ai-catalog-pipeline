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


class ReconciliationError(ValueError):
    """Unsupported or ambiguous scan data; no partial trust of malformed data."""


def _synthetic(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _URN.fullmatch(value):
        raise ReconciliationError(f"{field}: synthetic URN required")
    return value


def _int(value: Any, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ReconciliationError(f"{field}: integer outside allowed range")
    return value


def assess_scan(scan: dict[str, Any], *, retry_budget: int = 3,
                prior_complete_count: int | None = None) -> dict[str, Any]:
    """Classify a bounded synthetic scan without performing IO or inferring deletions.

    A successful terminal page proves only that the *fixture claims* an endpoint.
    The returned resume cursor is a proposal, not a persisted atomic checkpoint.
    """
    _int(retry_budget, "retry_budget", 0, 20)
    if prior_complete_count is not None:
        _int(prior_complete_count, "prior_complete_count", 0, 1_000_000)
    if not isinstance(scan, dict) or scan.keys() != _SCAN_KEYS:
        raise ReconciliationError("scan: missing or extra fields")
    if scan["schema_version"] != _VERSION or scan["synthetic"] is not True:
        raise ReconciliationError("scan: only explicit synthetic draft fixtures allowed")
    for field in ("source_id", "scan_id", "window_id", "root_cursor", "start_cursor"):
        _synthetic(scan[field], field)
    if scan["mode"] not in ("full", "incremental"):
        raise ReconciliationError("mode: full or incremental required")
    if scan["mode"] == "full" and scan["start_cursor"] != scan["root_cursor"]:
        raise ReconciliationError("full scan must start at explicit root cursor")
    _int(scan["attempts"], "attempts", 0, 1_000_000)
    pages = scan["pages"]
    if not isinstance(pages, list) or not 1 <= len(pages) <= _MAX_PAGES:
        raise ReconciliationError("pages: nonempty bounded list required")
    expected = scan["start_cursor"]
    seen_cursors: set[str] = set()
    record_ids: set[str] = set()
    failure: str | None = None
    completed = False
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or page.keys() != _PAGE_KEYS:
            raise ReconciliationError("page: missing or extra fields")
        cursor = _synthetic(page["cursor"], "cursor")
        if cursor != expected or cursor in seen_cursors:
            raise ReconciliationError("page: cursor gap, cycle, or unexpected order")
        seen_cursors.add(cursor)
        status = page["status"]
        if not isinstance(status, str) or status not in _STATES:
            raise ReconciliationError("page: unknown source status")
        ids = page["record_ids"]
        if (not isinstance(ids, list) or len(ids) > _MAX_IDS_PER_PAGE
                or len(ids) != len(set(x for x in ids if isinstance(x, str)))):
            raise ReconciliationError("page: invalid or duplicate record IDs")
        for item in ids:
            _synthetic(item, "record_id")
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


def compare_window(full: dict[str, Any], incremental: dict[str, Any]) -> dict[str, Any]:
    """Compare synthetic rehydrated same-window outputs, not live crawl parity."""
    for report, mode in ((full, "full"), (incremental, "incremental")):
        if (not isinstance(report, dict) or report.get("schema_version") != _VERSION
                or report.get("synthetic") is not True or report.get("mode") != mode
                or report.get("publication_eligible") is not False
                or report.get("deletion_inferred") is not False):
            raise ReconciliationError("comparison: expected synthetic assessment output")
    if full["source_id"] != incremental["source_id"] or full["window_id"] != incremental["window_id"]:
        raise ReconciliationError("comparison: exact source and observation window must match")
    if not full["window_complete"] or not incremental["window_complete"]:
        outcome = "insufficient_coverage"
    else:
        outcome = "matched" if full["record_ids"] == incremental["record_ids"] else "divergent"
    return {"synthetic": True, "publication_eligible": False, "outcome": outcome,
            "requires_review": outcome != "matched", "deletion_inferred": False}
