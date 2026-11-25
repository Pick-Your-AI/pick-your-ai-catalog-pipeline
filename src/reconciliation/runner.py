"""Caller-ticked reconciliation of bounded synthetic JSON bytes, offline only.

The caller retains fixture bytes. JobLedger stores only digests and checkpoints.
Staging costs one simulated quota unit; each page attempt costs another. There is
no transport, timer, body store, publication, or cross-store atomic transaction.
"""
from __future__ import annotations

import hashlib
import json
import re

from src.jobs.ledger import JobError, JobLedger
from src.reconciliation import ReconciliationError, assess_scan


class RunnerError(ValueError):
    """Fixed diagnostic; submitted content is never reflected."""


def _capture_policy(value):
    """Detach plain primitives once, before validation or any ledger wait.

    Bounds match the ledger's accepted envelope space without using its private
    helpers. No caller serialization/copy hooks run. Concurrent mutation during
    this initial traversal is not an atomic snapshot; callers must synchronize it.
    """
    remaining = 256

    def take(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 4:
            raise RunnerError("invalid_policy_envelope")
        kind = type(item)
        if item is None or kind is bool:
            return item
        if kind is str and len(item) <= 256:
            return item
        if kind is int and -1_000_000 <= item <= 1_000_000:
            return item
        if (kind is not dict and kind is not list) or len(item) > 32:
            raise RunnerError("invalid_policy_envelope")
        result = {} if kind is dict else []
        for index, entry in enumerate(item.items() if kind is dict else item):
            # Bound traversal even if a caller grows a container during capture.
            if index >= 32:
                raise RunnerError("invalid_policy_envelope")
            if kind is dict:
                key, child = entry
                if type(key) is not str or len(key) > 256:
                    raise RunnerError("invalid_policy_envelope")
                result[key] = take(child, depth + 1)
            else:
                result.append(take(entry, depth + 1))
        return result

    try:
        return take(value)
    except RuntimeError:  # Concurrent dictionary resize is invalid input.
        pass
    raise RunnerError("invalid_policy_envelope") from None


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _identity(value):
    return "urn:pya:synthetic:reconciliation:" + _hash(_encoded(value))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunnerError("invalid_fixture")
        result[key] = value
    return result


def _fixture(raw):
    # Immutable bytes avoid retaining arbitrary caller mappings or callbacks.
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise RunnerError("invalid_fixture")
    try:
        packet = json.loads(raw, object_pairs_hook=_pairs)
        if (type(packet) is not dict
                or set(packet) != {"scan", "retry_budget", "retry_after", "prior_complete_count"}):
            raise RunnerError("invalid_fixture")
        if type(packet["retry_budget"]) is not int or not 1 <= packet["retry_budget"] <= 8:
            raise RunnerError("invalid_fixture")
        if type(packet["retry_after"]) is not int or not 1 <= packet["retry_after"] <= 3600:
            raise RunnerError("invalid_fixture")
        scan = packet["scan"]
        # Narrower orchestration bounds reserve capacity in the existing ledger.
        if (type(scan) is not dict or type(scan.get("attempts")) is not int
                or scan["attempts"] != 0 or type(scan.get("pages")) is not list
                or not 1 <= len(scan["pages"]) <= 16):
            raise RunnerError("invalid_fixture")
        for page in scan["pages"]:
            if (type(page) is not dict or type(page.get("record_ids")) is not list
                    or len(page["record_ids"]) > 32):
                raise RunnerError("invalid_fixture")
        assess_scan(scan, retry_budget=packet["retry_budget"],
                    prior_complete_count=packet["prior_complete_count"])
        return packet
    except (ValueError, TypeError, RecursionError, OverflowError):
        pass
    raise RunnerError("invalid_fixture") from None


def _parser(parser):
    if (type(parser) is not str or len(parser) > 80
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", parser) is None):
        raise RunnerError("invalid_parser")


class FixtureRunner:
    """One successful page or failed attempt per explicit tick; no implicit loop.

    Stage IDs are retained by callers across restart. A stage binds exact fixture
    bytes, request, decision and parser. Repair requires a new scan identity.
    Reports are always rebuilt from digest-checked bytes and committed page jobs;
    no caller report or source-completeness assertion is accepted as evidence.
    """

    def __init__(self, ledger):
        if type(ledger) is not JobLedger:
            raise RunnerError("job_ledger_required")
        self.ledger = ledger

    @staticmethod
    def page_run_id(stage, index):
        """Return the stable page run identity used for ledger admission."""
        if (type(stage) is not str or len(stage) != 64
                or re.fullmatch(r"[a-f0-9]{64}", stage) is None
                or type(index) is not int or not 0 <= index < 16):
            raise RunnerError("invalid_page_identity")
        return _identity([stage, "page", index])

    @staticmethod
    def _descriptor(stage, index, digest):
        return [{"id": _identity([stage, index]), "digest": digest}]

    def _result(self, stage, packet, pages, checkpoint, state, reason, page_job=None):
        report = None
        if pages:
            scan = {**packet["scan"], "pages": pages}
            if pages[-1]["status"] != "ok" and page_job is not None:
                scan["attempts"] = self.ledger.snapshot(page_job)["attempts"]
            report = assess_scan(scan, retry_budget=packet["retry_budget"],
                                 prior_complete_count=packet["prior_complete_count"])
        return {"synthetic": True, "evidence_level": "synthetic_unverified",
                "rights_cleared": False, "publication_eligible": False,
                "stage_id": stage, "page_job_id": page_job, "state": state,
                "reason": reason, "checkpoint": checkpoint, "report": report,
                "unvisited_cursors": [p["cursor"] for p in packet["scan"]["pages"][len(pages):]],
                "last_known_preserved": True, "deletion_inferred": False,
                "withdrawal_inferred": False}

    def stage(self, raw, request, decision, parser_version, *, now):
        """Admit then commit an immutable fixture digest and its starting cursor.

        An interrupted ready admission can be resumed by repeating stage exactly.
        A done stage replay rechecks policy and never spends a second quota unit.
        """
        request, decision = _capture_policy(request), _capture_policy(decision)
        packet = _fixture(raw)
        _parser(parser_version)
        scan = packet["scan"]
        if (type(request) is not dict or any(type(key) is not str for key in request)
                or type(request.get("source_id")) is not str
                or request["source_id"] != scan["source_id"]):
            raise RunnerError("source_mismatch")
        stage = self.ledger.admit(scan["scan_id"], request, decision, parser_version, now=now)
        snapshot = self.ledger.snapshot(stage)
        if snapshot["state"] in {"ready", "retry"} and self.ledger.next_ready(now=now) != stage:
            return self._result(stage, packet, [], None, "waiting", "ledger_not_ready")
        receipt = self.ledger.attempt(
            stage, request, decision, now=now,
            observations=self._descriptor(stage, "fixture", _hash(raw)),
            checkpoint=scan["start_cursor"])
        return self._result(stage, packet, [], scan["start_cursor"] if receipt["state"] == "done" else snapshot["checkpoint"],
                            "staged" if receipt["state"] == "done" else receipt["state"],
                            receipt["reason"])

    def tick(self, stage, raw, request, decision, parser_version, *, now):
        """Verify recovery material/current policy and commit at most one page.

        Independent callers may replay the same deterministic page transaction;
        ledger serialization makes its success idempotent, not a network lease.
        """
        request, decision = _capture_policy(request), _capture_policy(decision)
        packet = _fixture(raw)
        _parser(parser_version)
        scan = packet["scan"]
        snapshot = self.ledger.snapshot(stage)
        if (snapshot["parser_version"] != parser_version
                or snapshot["run_id"] != scan["scan_id"]
                or snapshot["source_id"] != scan["source_id"]):
            raise RunnerError("stage_identity_mismatch")
        descriptors = self._descriptor(stage, "fixture", _hash(raw))
        expected = [(d["id"], d["digest"]) for d in descriptors]
        actual = [(d["logical_id"], d["digest"]) for d in snapshot["observations"]]
        if snapshot["state"] != "done" or actual != expected:
            raise RunnerError("fixture_not_staged_or_digest_mismatch")
        receipt = self.ledger.attempt(stage, request, decision, now=now,
                                      observations=descriptors, checkpoint=scan["start_cursor"])
        if receipt["state"] != "done":
            return self._result(stage, packet, [], snapshot["checkpoint"],
                                "refused", receipt["reason"])
        pages, checkpoint = [], scan["start_cursor"]
        for index, page in enumerate(scan["pages"]):
            run = self.page_run_id(stage, index)
            job = self.ledger.admit(run, request, decision, parser_version, now=now)
            current = self.ledger.snapshot(job)
            failed = page["status"] != "ok"
            descriptors = self._descriptor(stage, index, _hash(_encoded(page)))
            if current["state"] == "done":
                receipt = self.ledger.attempt(job, request, decision, now=now,
                                              observations=descriptors, checkpoint=page["next_cursor"])
                if receipt["state"] != "done":
                    return self._result(stage, packet, pages, checkpoint,
                                        "refused", receipt["reason"], job)
                pages.append(page)
                checkpoint = page["next_cursor"]
                continue
            if failed and current["attempts"]:
                # A crash after the failed attempt but before cancellation is safe.
                if current["state"] == "retry" and current["attempts"] >= packet["retry_budget"]:
                    self.ledger.cancel(job, now=now)
                    current = self.ledger.snapshot(job)
            if current["state"] in {"dead", "cancelled"}:
                reason = ("retry_budget_exhausted" if current["state"] == "cancelled"
                          else current["receipts"][-1]["reason"])
                return self._result(stage, packet, pages + ([page] if failed and current["attempts"] else []),
                                    checkpoint, "escalate", reason, job)
            if self.ledger.next_ready(now=now) != job:
                return self._result(stage, packet, pages + ([page] if failed and current["attempts"] else []),
                                    checkpoint, "waiting", "ledger_not_ready", job)
            try:
                receipt = self.ledger.attempt(
                    job, request, decision, now=now,
                    outcome=("rate_limited" if page["status"] == "quota_paused" else "unavailable") if failed else "accepted",
                    observations=[] if failed else descriptors,
                    checkpoint=None if failed else page["next_cursor"],
                    retry_after=packet["retry_after"] if failed else 0)
            except JobError as error:
                # Another local driver can change the scheduler after next_ready.
                if str(error) != "not_scheduled":
                    raise
                return self._result(stage, packet, pages, checkpoint, "waiting", "ledger_not_ready", job)
            if failed:
                current = self.ledger.snapshot(job)
                if receipt["state"] == "retry" and current["attempts"] >= packet["retry_budget"]:
                    self.ledger.cancel(job, now=now)
                    receipt = {"state": "cancelled", "reason": "retry_budget_exhausted"}
                return self._result(stage, packet, pages + ([page] if current["attempts"] else []), checkpoint,
                                    "degraded" if receipt["state"] == "retry" else "escalate", receipt["reason"], job)
            if receipt["state"] != "done":
                return self._result(stage, packet, pages, checkpoint, "escalate", receipt["reason"], job)
            pages.append(page)
            checkpoint = page["next_cursor"]
            return self._result(stage, packet, pages, checkpoint,
                                "complete" if checkpoint is None else "partial", "accepted", job)
        return self._result(stage, packet, pages, checkpoint,
                            "complete" if checkpoint is None else "partial", "replayed")
