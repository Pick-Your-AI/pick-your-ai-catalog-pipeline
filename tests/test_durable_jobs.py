"""Temporary SQLite files and synthetic inputs only; no transport/production evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from src.jobs.ledger import JobError, JobLedger


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-11-18T10:30:00Z"
LATER = "2026-11-18T10:31:00Z"
RUN = "urn:pya:synthetic:run:one"
OBS = [{"id": "urn:pya:synthetic:observation:one", "digest": hashlib.sha256(b"synthetic").hexdigest()}]
CURSOR = "urn:pya:synthetic:cursor:end"


class DurableJobsTests(unittest.TestCase):
    def setUp(self):
        packet = json.loads((ROOT / "tests/fixtures/synthetic-acquisition.json").read_text())
        self.request, self.decision = packet["request"], packet["decision"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.db"
        self.budgets = {self.request["source_id"]: 100}
        self.ledger = JobLedger(self.path, self.budgets)
        self.addCleanup(lambda: self.ledger.close())

    def admit(self, request=None, decision=None, run=RUN, parser="parser-v1"):
        return self.ledger.admit(run, request or self.request, decision or self.decision, parser, now=NOW)

    def accept(self, job, **kwargs):
        return self.ledger.attempt(job, self.request, self.decision, now=NOW,
                                   observations=OBS, checkpoint=CURSOR, **kwargs)

    def reopen(self):
        self.ledger.close()
        self.ledger = JobLedger(self.path, self.budgets)

    def test_reopen_and_repeat_commits_one_observation_and_checkpoint(self):
        job = self.admit()
        self.assertEqual(job, self.admit())
        self.assertEqual(self.accept(job)["state"], "done")
        before = self.ledger.snapshot(job)
        self.reopen()
        self.assertEqual(self.accept(job)["state"], "done")
        self.assertEqual(before, self.ledger.snapshot(job))
        self.assertEqual(before["attempts"], 1)
        self.assertEqual(before["checkpoint"], CURSOR)
        self.assertEqual(len(before["observations"]), 1)
        self.assertIsNone(self.ledger.next_ready(now=NOW))
        for key in ("rights_cleared", "publication_eligible"):
            self.assertIs(before[key], False)
        schema = json.loads((ROOT / "schemas/ingestion-run.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(before)
        for key, value in (("synthetic", False), ("publication_eligible", True), ("raw_body", "secret"), ("attempts", 9), ("run_id", RUN + "\n"), ("parser_version", "v1\n")):
            invalid = {**before, key: value}
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(invalid)))

    def test_duplicate_admission_persists_clock_across_reopen(self):
        job = self.admit()
        later = "2026-11-18T10:55:00Z"
        self.assertEqual(job, self.ledger.admit(RUN, self.request, self.decision,
                                             "parser-v1", now=later))
        self.reopen()
        before = self.ledger.snapshot(job)
        for request in (self.request, {**self.request, "id": "urn:pya:synthetic:request:new"}):
            with self.subTest(request=request["id"]), self.assertRaisesRegex(JobError, "clock_regressed"):
                self.ledger.admit(RUN, request, self.decision, "parser-v1",
                                  now="2026-11-18T10:40:00Z")
        self.assertEqual(self.ledger.snapshot(job), before)
        self.assertEqual(self.ledger.next_ready(now=later), job)

    def test_same_instant_duplicate_admission_is_idempotent_after_reopen(self):
        job = self.admit()
        before = self.ledger.snapshot(job)
        self.assertEqual(job, self.admit())
        self.reopen()
        self.assertEqual(job, self.admit())
        self.assertEqual(self.ledger.snapshot(job), before)
        self.assertEqual(self.ledger._db.execute("SELECT used FROM sources").fetchone()[0], 0)

    def test_duplicate_admission_at_expiry_dead_letters_ready_and_retry_jobs(self):
        retry = self.admit()
        request = {**self.request, "id": "urn:pya:synthetic:request:ready"}
        ready = self.admit(request=request)
        self.ledger.attempt(retry, self.request, self.decision, now=NOW, outcome="timeout")
        before = {job: self.ledger.snapshot(job) for job in (ready, retry)}
        expiry = self.decision["expires_at"]
        self.reopen()
        for job, envelope in ((ready, request), (retry, self.request)):
            with self.subTest(prior_state=before[job]["state"]):
                self.assertEqual(job, self.ledger.admit(RUN, envelope, self.decision,
                                                      "parser-v1", now=expiry))
        self.reopen()
        for job, envelope in ((ready, request), (retry, self.request)):
            with self.subTest(job=job):
                after = self.ledger.snapshot(job)
                self.assertEqual(after["state"], "dead")
                self.assertEqual(after["attempts"], before[job]["attempts"])
                self.assertEqual(after["receipts"][:-1], before[job]["receipts"])
                self.assertEqual(after["receipts"][-1]["reason"], "decision_inactive")
                self.assertEqual(after["receipts"][-1]["at"], self.ledger._db.execute("SELECT clock FROM meta").fetchone()[0])
                self.ledger.admit(RUN, envelope, self.decision, "parser-v1", now=expiry)
                self.assertEqual(after, self.ledger.snapshot(job))
        self.assertIsNone(self.ledger.next_ready(now=expiry))
        self.assertEqual(self.ledger._db.execute("SELECT used FROM sources").fetchone()[0], 1)
        self.assertEqual(self.ledger._db.execute("SELECT used FROM decisions").fetchone()[0], 1)

    def test_duplicate_completed_admission_retains_result_and_separate_refusal(self):
        job = self.admit()
        self.accept(job)
        before = self.ledger.snapshot(job)
        expiry = self.decision["expires_at"]
        self.reopen()
        self.assertEqual(job, self.ledger.admit(RUN, self.request, self.decision,
                                             "parser-v1", now=expiry))
        self.reopen()
        after = self.ledger.snapshot(job)
        self.assertEqual({**after, "receipts": before["receipts"]}, before)
        self.assertEqual(after["receipts"][:-1], before["receipts"])
        self.assertEqual(after["receipts"][-1]["state"], "refused")
        self.assertEqual(after["receipts"][-1]["reason"], "decision_inactive")
        self.ledger.admit(RUN, self.request, self.decision, "parser-v1", now=expiry)
        self.assertEqual(after, self.ledger.snapshot(job))
        self.assertEqual(self.ledger._db.execute("SELECT used FROM sources").fetchone()[0], 1)
        self.assertEqual(self.ledger._db.execute("SELECT used FROM decisions").fetchone()[0], 1)
        self.assertIsNone(self.ledger.next_ready(now=expiry))
        with self.assertRaisesRegex(JobError, "clock_regressed"):
            self.ledger.admit(RUN, self.request, self.decision, "parser-v1", now=LATER)

    def test_duplicate_admission_cannot_reopen_dead_or_cancelled_jobs(self):
        dead = self.admit()
        request = {**self.request, "id": "urn:pya:synthetic:request:cancelled"}
        cancelled = self.admit(request=request)
        self.ledger.attempt(dead, self.request, self.decision, now=NOW, outcome="parse_failed")
        self.ledger.cancel(cancelled, now=NOW)
        before = {job: self.ledger.snapshot(job) for job in (dead, cancelled)}
        for instant in (LATER, self.decision["expires_at"]):
            for job, envelope in ((dead, self.request), (cancelled, request)):
                self.assertEqual(job, self.ledger.admit(RUN, envelope, self.decision,
                                                      "parser-v1", now=instant))
                self.assertEqual(before[job], self.ledger.snapshot(job))
        self.reopen()
        for job in (dead, cancelled):
            self.assertEqual(before[job], self.ledger.snapshot(job))
        with self.assertRaisesRegex(JobError, "clock_regressed"):
            self.ledger.admit(RUN, request, self.decision, "parser-v1", now=LATER)

    def test_all_identity_dimensions_are_bound_and_observations_dedupe_across_runs(self):
        job = self.admit()
        self.accept(job)
        other = self.admit(run="urn:pya:synthetic:run:two")
        self.accept(other)
        self.assertEqual(self.ledger._db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)
        self.assertNotEqual(job, other)
        for key in ("id", "source_id", "locator", "fields"):
            request = deepcopy(self.request)
            request[key] = (["metadata.label"] if key == "fields" else "https://example.invalid/other" if key == "locator" else "urn:pya:synthetic:other")
            result = self.ledger.attempt(job, request, self.decision, now=NOW, observations=OBS, checkpoint=CURSOR)
            self.assertEqual(result["state"], "refused")
        with self.assertRaisesRegex(JobError, "identity_conflict"):
            self.admit(parser="parser-v2")
        request = {**self.request, "fields": ["metadata.label"]}
        with self.assertRaisesRegex(JobError, "identity_conflict"):
            self.admit(request=request)
        self.assertEqual(self.ledger.snapshot(job)["state"], "done")

    def test_current_rights_checked_after_reopen_on_retry_and_completed_replay(self):
        for completed in (False, True):
            for change in ("missing", "revoked", "conditional", "expired", "revision", "malformed"):
                with self.subTest(completed=completed, change=change), tempfile.TemporaryDirectory() as directory:
                    ledger = JobLedger(Path(directory) / "test.db", self.budgets)
                    try:
                        job = ledger.admit(RUN, self.request, self.decision, "v1", now=NOW)
                        ledger.attempt(job, self.request, self.decision, now=NOW, outcome="accepted" if completed else "timeout")
                        ledger.close()
                        ledger = JobLedger(Path(directory) / "test.db", self.budgets)
                        decision = deepcopy(self.decision)
                        if change == "missing":
                            decision = None
                        elif change == "revoked":
                            decision["status"] = "revoked"
                        elif change == "conditional":
                            decision["conditions"] = ["attribution_required"]
                        elif change == "expired":
                            decision["expires_at"] = LATER
                        elif change == "revision":
                            decision["revision"] = 2
                        else:
                            decision["retention"]["storage"] = "disk"
                        result = ledger.attempt(job, self.request, decision, now=LATER)
                        self.assertEqual(result["state"], "refused" if completed else "dead")
                        self.assertEqual(ledger.snapshot(job)["attempts"], 1)
                        self.assertGreaterEqual(len(ledger.snapshot(job)["receipts"]), 3)
                    finally:
                        ledger.close()

    def test_backpressure_fairness_and_cancellation_survive_reopen(self):
        self.ledger.close()
        other_request = {**self.request, "id": "urn:pya:synthetic:request:other", "source_id": "urn:pya:synthetic:source:other"}
        other_decision = {**self.decision, "id": "urn:pya:synthetic:decision:other", "source_id": other_request["source_id"]}
        self.budgets[other_request["source_id"]] = 100
        self.ledger = JobLedger(self.path.parent / "fair.db", self.budgets)
        self.path = self.path.parent / "fair.db"
        first = self.admit()
        second = self.admit(request={**self.request, "id": "urn:pya:synthetic:request:two"})
        other = self.admit(request=other_request, decision=other_decision)
        self.assertEqual(self.ledger.next_ready(now=NOW), first)
        self.ledger.attempt(first, self.request, self.decision, now=NOW, outcome="rate_limited", retry_after=60)
        self.reopen()
        self.assertEqual(self.ledger.next_ready(now=NOW), other)
        self.ledger.attempt(other, other_request, other_decision, now=NOW)
        self.assertIsNone(self.ledger.next_ready(now="2026-11-18T10:30:59.999999Z"))
        with self.assertRaisesRegex(JobError, "not_scheduled"):
            self.ledger.attempt(first, self.request, self.decision, now=NOW)
        self.assertEqual(self.ledger.next_ready(now=LATER), first)
        self.ledger.cancel(first, now=LATER)
        self.assertEqual(self.ledger.next_ready(now=LATER), second)
        self.assertEqual(self.ledger.attempt(first, self.request, self.decision, now=LATER)["state"], "cancelled")
        self.assertEqual(self.ledger.snapshot(first)["attempts"], 1)

    def test_successful_source_yields_to_other_ready_source(self):
        self.ledger.close()
        request = {**self.request, "id": "urn:pya:synthetic:request:other", "source_id": "urn:pya:synthetic:source:other"}
        decision = {**self.decision, "id": "urn:pya:synthetic:decision:other", "source_id": request["source_id"]}
        self.budgets[request["source_id"]] = 100
        self.path = self.path.parent / "turns.db"
        self.ledger = JobLedger(self.path, self.budgets)
        first = self.admit()
        self.admit(request={**self.request, "id": "urn:pya:synthetic:request:two"})
        other = self.admit(request=request, decision=decision)
        self.accept(first)
        self.assertEqual(self.ledger.next_ready(now=NOW), other)

    def test_source_and_decision_quotas_are_persistent_across_requests_and_runs(self):
        for source_budget in (1, 100):
            with self.subTest(source_budget=source_budget), tempfile.TemporaryDirectory() as directory:
                budgets = {self.request["source_id"]: source_budget}
                ledger = JobLedger(Path(directory) / "quota.db", budgets)
                decision = {**self.decision, "max_simulated_calls": 100 if source_budget == 1 else 1}
                first = ledger.admit(RUN, self.request, decision, "v1", now=NOW)
                ledger.attempt(first, self.request, decision, now=NOW)
                ledger.close()
                ledger = JobLedger(Path(directory) / "quota.db", budgets)
                try:
                    request = {**self.request, "id": "urn:pya:synthetic:request:two"}
                    second = ledger.admit("urn:pya:synthetic:run:two", request, decision, "v1", now=NOW)
                    result = ledger.attempt(second, request, decision, now=NOW)
                    self.assertEqual(result["reason"], "quota_exhausted")
                    self.assertEqual(ledger.snapshot(second)["attempts"], 0)
                    with self.assertRaisesRegex(JobError, "budget_configuration_changed"):
                        JobLedger(Path(directory) / "quota.db", {self.request["source_id"]: 2})
                finally:
                    ledger.close()

    def test_retry_exhaustion_and_permanent_failures_keep_dead_letters(self):
        self.decision["max_simulated_calls"] = 100
        job = self.admit()
        for number in range(8):
            now = f"2026-11-18T10:30:{number:02d}Z"
            result = self.ledger.attempt(job, self.request, self.decision, now=now, outcome="unavailable")
        self.assertEqual(result["reason"], "attempts_exhausted")
        self.reopen()
        snapshot = self.ledger.snapshot(job)
        self.assertEqual(snapshot["state"], "dead")
        self.assertEqual(len(snapshot["receipts"]), 9)
        self.assertEqual(snapshot["receipts"][-1]["attempt"], 8)
        for outcome in ("parse_failed", "validation_failed"):
            request = {**self.request, "id": f"urn:pya:synthetic:request:{outcome}"}
            another = self.ledger.admit(RUN, request, self.decision, "v1", now=LATER)
            result = self.ledger.attempt(another, request, self.decision, now=LATER, outcome=outcome)
            self.assertEqual(result["state"], "dead")
            self.assertEqual(self.ledger.snapshot(another)["attempts"], 1)

    def test_missing_admission_rights_retains_receipt_without_queueing(self):
        job = self.ledger.admit(RUN, self.request, None, "v1", now=NOW)
        self.assertEqual(self.ledger.snapshot(job)["receipts"][0]["reason"], "missing_decision")
        self.assertEqual(self.ledger.snapshot(job)["state"], "dead")
        self.assertIsNone(self.ledger.next_ready(now=NOW))

    def test_conflicting_completion_and_cross_run_observation_preserve_history(self):
        job = self.admit()
        self.accept(job)
        changed = [{**OBS[0], "digest": "f" * 64}]
        result = self.ledger.attempt(job, self.request, self.decision, now=NOW, observations=changed)
        self.assertEqual(result["reason"], "completion_conflict")
        another = self.admit(run="urn:pya:synthetic:run:two")
        result = self.ledger.attempt(another, self.request, self.decision, now=NOW, observations=changed)
        self.assertEqual(result["reason"], "observation_conflict")
        self.assertEqual(self.ledger.snapshot(another)["observations"], [])
        self.assertEqual(self.ledger.snapshot(job)["observations"][0]["digest"], OBS[0]["digest"])

    def test_sqlite_abort_rolls_back_observations_checkpoint_quota_and_receipt(self):
        job = self.admit()
        before = self.ledger.snapshot(job)
        self.ledger._db.execute("CREATE TRIGGER interrupt BEFORE UPDATE OF checkpoint ON jobs BEGIN SELECT RAISE(ABORT, 'synthetic interruption'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.accept(job)
        self.assertEqual(self.ledger.snapshot(job), before)
        self.assertEqual(self.ledger._db.execute("SELECT used FROM sources").fetchone()[0], 0)
        self.assertEqual(self.ledger._db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
        self.assertEqual(self.ledger._db.execute("SELECT count(*) FROM decisions").fetchone()[0], 0)
        self.ledger._db.execute("DROP TRIGGER interrupt")
        self.reopen()
        self.accept(job)
        self.assertEqual(self.ledger.snapshot(job)["attempts"], 1)

    def test_process_interruption_before_commit_and_after_commit_reopens_cleanly(self):
        job = self.admit()
        self.ledger.close()
        script = '''
import json, os, sys
from pathlib import Path
from src.jobs.ledger import JobLedger
packet = json.loads(Path("tests/fixtures/synthetic-acquisition.json").read_text())
class Interrupted(JobLedger):
    def _finish(self, job, state, reason):
        result = super()._finish(job, state, reason)
        if state == "done" and sys.argv[3] == "before":
            os._exit(71)
        return result
ledger = Interrupted(sys.argv[1], {packet["request"]["source_id"]: 100})
ledger.attempt(sys.argv[2], packet["request"], packet["decision"], now="2026-11-18T10:30:00Z", observations=json.loads(sys.argv[4]), checkpoint=sys.argv[5])
os._exit(72)
'''
        for mode, code in (("before", 71), ("after", 72)):
            result = subprocess.run([sys.executable, "-c", script, str(self.path), job, mode, json.dumps(OBS), CURSOR], cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stderr.decode())
            self.ledger = JobLedger(self.path, self.budgets)
            snapshot = self.ledger.snapshot(job)
            self.assertEqual(snapshot["state"], "ready" if mode == "before" else "done")
            self.assertEqual(snapshot["attempts"], 0 if mode == "before" else 1)
            self.assertEqual(len(snapshot["observations"]), 0 if mode == "before" else 1)
            self.assertEqual(snapshot["checkpoint"], None if mode == "before" else CURSOR)
            self.ledger.close()
        self.ledger = JobLedger(self.path, self.budgets)
        before = self.ledger.snapshot(job)
        self.accept(job)
        self.assertEqual(self.ledger.snapshot(job), before)

    def test_strict_bounds_and_no_raw_source_content_or_secrets_retained(self):
        job = self.admit()
        before = self.ledger.snapshot(job)
        cases = [{"retry_after": True}, {"retry_after": 3601}, {"outcome": "untrusted_secret"},
                 {"observations": [{**OBS[0], "body": "untrusted_secret"}]},
                 {"observations": OBS * 2}, {"observations": OBS * 33},
                 {"checkpoint": "untrusted_secret"}, {"outcome": "timeout", "checkpoint": CURSOR}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(JobError) as error:
                self.ledger.attempt(job, self.request, self.decision, now=NOW, **case)
            self.assertNotIn("untrusted_secret", str(error.exception))
        self.assertEqual(before, self.ledger.snapshot(job))
        self.accept(job)
        self.assertNotIn(b"https://", self.path.read_bytes())
        self.assertNotIn(b"metadata.title", self.path.read_bytes())
        self.assertNotIn(b"untrusted_secret", self.path.read_bytes())
        with self.assertRaisesRegex(JobError, "clock_regressed"):
            self.ledger.cancel(job, now="2026-11-18T10:29:59Z")
        for budget in (True, 0, 101):
            with self.assertRaises(JobError):
                JobLedger(self.path, {self.request["source_id"]: budget})

    def test_snapshot_is_consistent_during_another_connections_commit(self):
        job = self.admit()
        before = self.ledger.snapshot(job)
        # WAL lets the writer really commit while the reader holds its read
        # snapshot; the production proposal does not change journal mode.
        self.assertEqual(self.ledger._db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        writer = self.ledger
        request, decision = self.request, self.decision

        class InterleavedReader(JobLedger):
            def _job(self, job_id):
                row = super()._job(job_id)
                writer.attempt(job_id, request, decision, now=NOW,
                               observations=OBS, checkpoint=CURSOR)
                return row

        reader = InterleavedReader(self.path, self.budgets)
        try:
            snapshot = reader.snapshot(job)
            self.assertEqual(writer.snapshot(job)["state"], "done")
            self.assertEqual(snapshot, before)
            self.assertEqual(reader.snapshot(job), writer.snapshot(job))
            self.assertFalse(reader._db.in_transaction)
            self.assertFalse(writer._db.in_transaction)
        finally:
            reader.close()

    def test_snapshot_releases_transaction_after_read_or_commit_failure(self):
        job = self.admit()
        for blocked in ("read", "commit"):
            def authorizer(action, first, second, database, trigger):
                if ((blocked == "read" and action == sqlite3.SQLITE_READ and first == "receipts") or
                        (blocked == "commit" and action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT")):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            self.ledger._db.set_authorizer(authorizer)
            try:
                with self.assertRaises(sqlite3.DatabaseError):
                    self.ledger.snapshot(job)
                self.assertFalse(self.ledger._db.in_transaction)
            finally:
                self.ledger._db.set_authorizer(None)
            self.assertEqual(self.ledger.snapshot(job)["state"], "ready")
        for identity in ("invalid", "f" * 64):
            with self.assertRaises(JobError):
                self.ledger.snapshot(identity)
            self.assertFalse(self.ledger._db.in_transaction)
        self.accept(job)
        self.assertEqual(self.ledger.snapshot(job)["state"], "done")

    def test_rollback_journal_interleaving_preserves_lock_error_and_cleanup(self):
        job = self.admit()
        before = self.ledger.snapshot(job)
        self.assertEqual(self.ledger._db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        writer = self.ledger
        request, decision = self.request, self.decision

        class InterleavedReader(JobLedger):
            def _job(self, job_id):
                row = super()._job(job_id)
                writer.attempt(job_id, request, decision, now=NOW,
                               observations=OBS, checkpoint=CURSOR)
                return row

        reader = InterleavedReader(self.path, self.budgets)
        try:
            # This synchronous test hook cannot release the reader until the
            # writer returns, so rollback journaling must surface its lock error.
            with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                reader.snapshot(job)
            self.assertFalse(reader._db.in_transaction)
            self.assertFalse(writer._db.in_transaction)
            self.assertEqual(writer.snapshot(job), before)
            self.accept(job)
            self.assertEqual(writer.snapshot(job)["state"], "done")
        finally:
            reader.close()

    def mutate_while_waiting(self, action, mutate):
        ready, start, waiting = (threading.Event() for _ in range(3))
        results, failures = [], []

        def worker():
            ledger = None
            try:
                ledger = JobLedger(self.path, self.budgets)
                ledger._db.set_trace_callback(lambda sql: waiting.set() if sql == "BEGIN IMMEDIATE" else None)
                ready.set()
                if not start.wait(5):
                    raise AssertionError("worker was not started")
                results.append(action(ledger))
                self.assertFalse(ledger._db.in_transaction)
            except BaseException as error:
                failures.append(error)
            finally:
                if ledger is not None:
                    ledger.close()

        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(ready.wait(5))
            self.ledger._db.execute("BEGIN IMMEDIATE")
            start.set()
            self.assertTrue(waiting.wait(5))
            mutate()
        finally:
            if self.ledger._db.in_transaction:
                self.ledger._db.execute("ROLLBACK")
            start.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        if failures:
            raise failures[0]
        return results[0]

    def test_observations_are_detached_before_writer_lock_wait(self):
        job = self.admit()
        observations = deepcopy(OBS)
        sentinel = "synthetic_unvalidated_sentinel\ninvalid"

        def mutate():
            observations[0].update(id=sentinel, digest=sentinel)
            observations.extend({"id": f"urn:pya:synthetic:observation:extra-{i}",
                                 "digest": OBS[0]["digest"]} for i in range(40))

        result = self.mutate_while_waiting(
            lambda ledger: ledger.attempt(job, self.request, self.decision, now=NOW,
                                          observations=observations, checkpoint=CURSOR), mutate)
        self.assertEqual(result["state"], "done")
        snapshot = self.ledger.snapshot(job)
        self.assertEqual([(o["logical_id"], o["digest"]) for o in snapshot["observations"]],
                         [(OBS[0]["id"], OBS[0]["digest"])])
        self.assertEqual(self.accept(job)["reason"], "accepted")
        self.assertEqual(self.ledger.snapshot(job), snapshot)
        Draft202012Validator(json.loads((ROOT / "schemas/ingestion-run.schema.json").read_text())).validate(snapshot)
        self.assertNotIn(sentinel.encode(), self.path.read_bytes())

    def test_request_and_decision_are_detached_at_each_call_boundary(self):
        request, decision = deepcopy(self.request), deepcopy(self.decision)

        def mutate():
            request["id"] = "synthetic_invalid_request\n"
            request["fields"].clear()
            decision["status"] = "revoked"
            decision["retention"]["storage"] = "synthetic_invalid_storage"

        job = self.mutate_while_waiting(
            lambda ledger: ledger.admit(RUN, request, decision, "parser-v1", now=NOW), mutate)
        self.assertEqual(job, self.admit())
        self.assertEqual(self.ledger.snapshot(job)["request_id"], self.request["id"])
        request, decision = deepcopy(self.request), deepcopy(self.decision)
        result = self.mutate_while_waiting(
            lambda ledger: ledger.attempt(job, request, decision, now=NOW), mutate)
        self.assertEqual(result["state"], "done")
        self.assertEqual(self.ledger._db.execute("SELECT id,revision,used FROM decisions").fetchone()[:],
                         (self.decision["id"], self.decision["revision"], 1))
        # An explicit new call observes the newly supplied policy, even on replay.
        decision = {**self.decision, "status": "revoked"}
        self.assertEqual(self.ledger.attempt(job, self.request, decision, now=NOW)["reason"],
                         "permission_not_unconditional")
        other = self.admit(run="urn:pya:synthetic:run:revoked")
        result = self.mutate_while_waiting(
            lambda ledger: ledger.attempt(other, self.request, decision, now=NOW),
            lambda: decision.update(status="permit"))
        self.assertEqual(result["state"], "dead")
        self.assertEqual(self.ledger.snapshot(other)["attempts"], 0)

    def test_constructor_detaches_budgets_before_sqlite_wait(self):
        budgets = dict(self.budgets)
        waiting, results, failures = threading.Event(), [], []
        connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_trace_callback(lambda sql: waiting.set() if "INSERT OR IGNORE INTO meta" in sql else None)
            return db

        def worker():
            try:
                ledger = JobLedger(self.path, budgets)
                try:
                    results.extend(tuple(row) for row in ledger._db.execute("SELECT id,budget FROM sources"))
                finally:
                    ledger.close()
            except BaseException as error:
                failures.append(error)

        with patch("src.jobs.ledger.sqlite3.connect", traced_connect):
            self.ledger._db.execute("BEGIN IMMEDIATE")
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(waiting.wait(5))
                budgets.clear()
                budgets["synthetic_invalid_source\n"] = 999999
            finally:
                self.ledger._db.execute("ROLLBACK")
                thread.join(5)
        self.assertFalse(thread.is_alive())
        if failures:
            raise failures[0]
        self.assertEqual(results, list(self.budgets.items()))
        self.reopen()

    def test_capture_bounds_unsupported_objects_and_initialization_cleanup(self):
        class Unsupported:
            def __deepcopy__(self, memo):
                raise AssertionError("must not copy caller objects")

        cyclic = []
        cyclic.append(cyclic)
        for invalid in (Unsupported(), cyclic, [0] * 10000, "x" * 10000, 10 ** 100):
            with self.subTest(kind=type(invalid).__name__):
                with patch("src.jobs.ledger.sqlite3.connect", side_effect=AssertionError("must reject before opening")):
                    with self.assertRaises(JobError):
                        JobLedger(self.path, invalid)
                with self.assertRaises(JobError):
                    self.ledger.admit(RUN, self.request, invalid, "v1", now=NOW)
                with self.assertRaises(JobError):
                    self.ledger.attempt("f" * 64, self.request, self.decision, now=NOW, observations=[invalid])
                self.assertFalse(self.ledger._db.in_transaction)
        job = self.admit()
        self.assertEqual(self.ledger.attempt(job, self.request, cyclic, now=NOW)["reason"], "invalid_policy_envelope")
        self.assertEqual(self.ledger.snapshot(job)["attempts"], 0)
        connections = []
        connect = sqlite3.connect

        def failed_setup(*args, **kwargs):
            db = connect(*args, **kwargs)
            connections.append(db)
            db.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
            return db

        with patch("src.jobs.ledger.sqlite3.connect", failed_setup), self.assertRaises(sqlite3.DatabaseError):
            JobLedger(self.path, self.budgets)
        with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
            connections[0].execute("SELECT 1")
        self.reopen()
