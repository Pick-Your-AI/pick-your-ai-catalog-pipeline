"""Existing-only recovery of module-owned temporary synthetic job ledgers."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src.jobs.ledger import JobError, JobLedger
from src.reconciliation.runner import FixtureRunner, RunnerError


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-11-18T10:30:00Z"
LATER = "2026-11-18T10:31:00Z"
RUN = "urn:pya:synthetic:run:recovery"


class ExistingJobRecoveryTests(unittest.TestCase):
    def setUp(self):
        packet = json.loads((ROOT / "tests/fixtures/synthetic-acquisition.json").read_text())
        self.request, self.decision = packet["request"], packet["decision"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite"
        self.budgets = {self.request["source_id"]: 100}

    def prepared(self, outcome="accepted"):
        with closing(JobLedger(self.path, self.budgets)) as ledger:
            job = ledger.admit(RUN, self.request, self.decision, "parser-v1", now=NOW)
            ledger.attempt(job, self.request, self.decision, now=NOW, outcome=outcome,
                           observations=[{"id": "urn:pya:synthetic:observation:recovery",
                                          "digest": "a" * 64}] if outcome == "accepted" else [])
            return job, ledger.snapshot(job)

    def test_existing_empty_and_completed_ledgers_reopen_without_writes(self):
        with closing(JobLedger(self.path, self.budgets)):
            pass
        before = self.path.read_bytes()
        with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
            self.assertIsNone(ledger.lookup_run(RUN, self.request["id"]))
        self.assertEqual(self.path.read_bytes(), before)
        job, snapshot = self.prepared()
        statements = []
        original = sqlite3.connect

        def traced(*args, **kwargs):
            db = original(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db

        before = self.path.read_bytes()
        with patch.object(sqlite3, "connect", side_effect=traced), closing(
                JobLedger.open_existing(self.path, self.budgets)) as ledger:
            self.assertEqual(ledger.snapshot(job), snapshot)
            self.assertEqual(ledger.lookup_run(RUN, self.request["id"]), job)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any(sql.lstrip().upper().startswith(
            ("CREATE", "INSERT", "UPDATE", "DELETE", "REPLACE")) for sql in statements))

    def test_retry_and_terminal_history_preserve_accounting(self):
        job, snapshot = self.prepared("unavailable")
        with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
            self.assertEqual(ledger.snapshot(job), snapshot)
            self.assertEqual(ledger.next_ready(now=LATER), job)
            ledger.attempt(job, self.request, self.decision, now=LATER)
            completed = ledger.snapshot(job)
        with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
            self.assertEqual(ledger.snapshot(job), completed)
            self.assertEqual(completed["attempts"], 2)
            self.assertEqual(ledger._db.execute("SELECT used FROM sources").fetchone()[0], 2)

    def test_missing_database_is_not_created_and_error_has_no_storage_chain(self):
        with self.assertRaisesRegex(JobError, "^corrupt_ledger$") as caught:
            JobLedger.open_existing(self.path, self.budgets)
        self.assertFalse(self.path.exists())
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_corruption_is_rejected_without_repairing_the_file(self):
        self.prepared()
        pristine = self.path.read_bytes()
        mutations = (
            "DELETE FROM meta", "DELETE FROM sources", "DELETE FROM decisions",
            "UPDATE sources SET used=0", "UPDATE sources SET served=0",
            "UPDATE jobs SET attempts=2", "UPDATE receipts SET attempt=NULL",
            "UPDATE receipts SET at=NULL", "UPDATE receipts SET reason=NULL",
            "UPDATE decisions SET used=2", "UPDATE meta SET turn=0",
            "UPDATE jobs SET state='ready'", "UPDATE jobs SET state='fixture_marker'",
            "UPDATE jobs SET run_id='urn:pya:synthetic:run:changed'",
            "UPDATE jobs SET completion_digest='" + "f" * 64 + "'",
            "UPDATE jobs SET checkpoint='urn:pya:synthetic:cursor:changed'",
            "UPDATE observations SET logical_id='urn:pya:synthetic:observation:changed'",
            "UPDATE receipts SET reason='fixture_marker' WHERE attempt=1",
            "UPDATE receipts SET state='retry' WHERE reason='accepted'",
            "DELETE FROM receipts WHERE reason='admitted'",
            "UPDATE receipts SET state='cancelled',reason='operator_cancelled' WHERE reason='admitted'",
            "CREATE TRIGGER recovery_fixture AFTER INSERT ON jobs BEGIN DELETE FROM meta; END",
        )
        for sql in mutations:
            with self.subTest(mutation=sql):
                self.path.write_bytes(pristine)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(sql)
                damaged = hashlib.sha256(self.path.read_bytes()).digest()
                with self.assertRaises(JobError):
                    JobLedger.open_existing(self.path, self.budgets)
                self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), damaged)

    def test_charged_completion_cannot_follow_cancellation(self):
        job, _ = self.prepared()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE receipts SET seq=3 WHERE seq=2")
            db.execute("""INSERT INTO receipts(seq,job,state,reason,attempt,at)
                SELECT 2,?,'cancelled','operator_cancelled',0,clock FROM meta""", (job,))
        damaged = self.path.read_bytes()
        with self.assertRaisesRegex(JobError, "^corrupt_ledger$"):
            JobLedger.open_existing(self.path, self.budgets)
        self.assertEqual(self.path.read_bytes(), damaged)

    def test_backoff_requires_a_retained_retry_and_cannot_disappear(self):
        for outcome in ("accepted", "unavailable"):
            with self.subTest(outcome=outcome):
                if self.path.exists():
                    self.path.unlink()  # Only this test's temporary synthetic fixture.
                self.prepared(outcome)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute("UPDATE sources SET until_at=" + (
                        "(SELECT clock+300000000 FROM meta)" if outcome == "accepted"
                        else "-62135596800000000"))
                damaged = self.path.read_bytes()
                with self.assertRaisesRegex(JobError, "^corrupt_ledger$"):
                    JobLedger.open_existing(self.path, self.budgets)
                self.assertEqual(self.path.read_bytes(), damaged)

    def test_later_charges_bound_retry_history(self):
        for contradiction in ("hold_after_success", "next_retry_before_minimum_delay"):
            with self.subTest(contradiction=contradiction):
                if self.path.exists():
                    self.path.unlink()  # Only this test's temporary synthetic fixture.
                job, _ = self.prepared("unavailable")
                with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
                    ledger.attempt(job, self.request, self.decision, now=LATER,
                                   outcome="accepted" if contradiction == "hold_after_success" else "unavailable")
                    if contradiction == "hold_after_success":
                        ledger.admit(RUN + ":pending", self.request, self.decision, "parser-v1", now=LATER)
                with closing(sqlite3.connect(self.path)) as db, db:
                    if contradiction == "hold_after_success":
                        db.execute("UPDATE sources SET until_at=(SELECT clock+300000000 FROM meta)")
                    else:
                        db.execute("UPDATE receipts SET at=(SELECT MIN(at)+500000 FROM receipts) WHERE attempt=2")
                        db.execute("UPDATE sources SET until_at=(SELECT MAX(at)+1000000 FROM receipts)")
                damaged = self.path.read_bytes()
                with self.assertRaisesRegex(JobError, "^corrupt_ledger$"):
                    JobLedger.open_existing(self.path, self.budgets)
                self.assertEqual(self.path.read_bytes(), damaged)

    def test_supplied_decision_cannot_reset_usage_with_a_contradictory_persisted_key(self):
        self.decision["max_simulated_calls"] = 1
        for outcome in ("accepted", "unavailable"):
            for column, value in (("id", "urn:pya:synthetic:decision:changed"), ("revision", 2)):
                with self.subTest(outcome=outcome, column=column):
                    if self.path.exists():
                        self.path.unlink()  # Only this test's temporary synthetic fixture.
                    job, before = self.prepared(outcome)
                    with closing(sqlite3.connect(self.path)) as db, db:
                        db.execute(f"UPDATE decisions SET {column}=?", (value,))
                    with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
                        result = ledger.attempt(job, self.request, self.decision, now=LATER)
                        self.assertEqual(result["reason"], "decision_binding_conflict")
                        self.assertEqual(result["state"], "refused" if outcome == "accepted" else "dead")
                        self.assertEqual(ledger.snapshot(job)["attempts"], before["attempts"])
                        self.assertEqual(ledger._db.execute("SELECT used FROM sources").fetchone()[0], 1)
                        self.assertEqual(ledger._db.execute("SELECT COUNT(*),SUM(used) FROM decisions").fetchone()[:], (1, 1))

    def test_fairness_order_must_match_charged_receipt_order(self):
        other_request = {**self.request, "source_id": "urn:pya:synthetic:source:other"}
        other_decision = {**self.decision, "id": "urn:pya:synthetic:decision:other",
                          "source_id": other_request["source_id"]}
        budgets = {self.request["source_id"]: 100, other_request["source_id"]: 100}
        with closing(JobLedger(self.path, budgets)) as ledger:
            for n, (request, decision) in enumerate(((self.request, self.decision),
                                                     (other_request, other_decision),
                                                     (self.request, self.decision))):
                job = ledger.admit(RUN + str(n), request, decision, "parser-v1", now=NOW)
                ledger.attempt(job, request, decision, now=NOW)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE sources SET served=CASE served WHEN 2 THEN 3 WHEN 3 THEN 2 END")
        damaged = self.path.read_bytes()
        with self.assertRaisesRegex(JobError, "^corrupt_ledger$"):
            JobLedger.open_existing(self.path, budgets)
        self.assertEqual(self.path.read_bytes(), damaged)

    def test_changed_budget_is_not_accepted_or_rewritten(self):
        self.prepared()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(JobError, "^corrupt_ledger$"):
            JobLedger.open_existing(self.path, {self.request["source_id"]: 99})
        self.assertEqual(self.path.read_bytes(), before)

    def test_lookup_is_bounded_and_never_admits_missing_work(self):
        job, snapshot = self.prepared()
        with closing(JobLedger.open_existing(self.path, self.budgets)) as ledger:
            self.assertEqual(ledger.lookup_run(RUN, self.request["id"]), job)
            self.assertIsNone(ledger.lookup_run(RUN + ":missing", self.request["id"]))
            with self.assertRaises(JobError):
                ledger.lookup_run("x" * 257, self.request["id"])
            self.assertEqual(ledger.snapshot(job), snapshot)
            self.assertEqual(ledger._db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)

    def test_page_identity_rejects_unbounded_or_nonbuiltin_inputs(self):
        for stage, index in (("a" * 63, 0), ("a" * 64, -1), ("a" * 64, 16),
                             ("a" * 64, True), ("a" * 64, 0.0), (object(), 0)):
            with self.subTest(index=index), self.assertRaisesRegex(RunnerError, "^invalid_page_identity$"):
                FixtureRunner.page_run_id(stage, index)
        self.assertNotEqual(FixtureRunner.page_run_id("a" * 64, 0),
                            FixtureRunner.page_run_id("a" * 64, 15))


if __name__ == "__main__":
    unittest.main()
