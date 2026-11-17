"""Synthetic source-health failure-path tests; no external IO or live privileges."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.reconciliation import ReconciliationError, assess_scan, compare_window

BASE = "urn:pya:synthetic:"


def page(cursor="page:0", next_cursor=None, status="ok", ids=("record:a",)):
    return {"cursor": BASE + cursor, "next_cursor": BASE + next_cursor if next_cursor else None,
            "status": status, "record_ids": [BASE + i for i in ids]}


def scan(mode="full", pages=None, **changes):
    original = {"schema_version": "reconciliation-draft-0.1.0", "synthetic": True,
                "source_id": BASE + "source:fictional", "scan_id": BASE + "scan:one",
                "window_id": BASE + "window:one", "mode": mode,
                "root_cursor": BASE + "page:0", "start_cursor": BASE + "page:0",
                "attempts": 0, "pages": [page()] if pages is None else pages}
    original.update(changes)
    return original


class ScanTests(unittest.TestCase):
    def test_complete_full_and_count_change_are_not_deletions(self):
        report = assess_scan(scan(), prior_complete_count=2)
        self.assertEqual(report["status"], "complete")
        self.assertTrue(report["full_coverage_claimed"])
        self.assertTrue(report["prior_count_changed"])
        self.assertIsNone(report["resume_cursor"])
        self.assertFalse(report["deletion_inferred"])
        self.assertFalse(report["withdrawal_inferred"])
        self.assertFalse(report["publication_eligible"])

    def test_cursor_chain_and_partial_resume(self):
        pages = [page(next_cursor="page:1"), page("page:1", "page:2", ids=("record:b",))]
        report = assess_scan(scan(pages=pages))
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["resume_cursor"], BASE + "page:2")
        self.assertIsNone(report["prior_count_changed"])
        self.assertEqual(report["record_count"], 2)
        self.assertTrue(report["last_known_preserved"])

    def test_incremental_cannot_claim_full_coverage(self):
        result = assess_scan(scan(mode="incremental"), prior_complete_count=99)
        self.assertTrue(result["window_complete"])
        self.assertFalse(result["full_coverage_claimed"])
        self.assertIsNone(result["prior_count_changed"])

    def test_failure_does_not_advance_cursor_or_infer_removal(self):
        for failure in ("parse_error", "broken_link", "quota_paused", "transport_error"):
            report = assess_scan(scan(pages=[page(next_cursor="page:1"),
                                             page("page:1", status=failure, ids=())]), retry_budget=3)
            self.assertEqual(report["status"], "degraded")
            self.assertEqual(report["resume_cursor"], BASE + "page:1")
            self.assertEqual(report["failure"], failure)
            self.assertFalse(report["deletion_inferred"])
            self.assertTrue(report["last_known_preserved"])
        self.assertEqual(report["next_action"], "retry_from_failing_cursor_if_rights_allow")

    def test_retry_budget_escalates_but_quota_stays_paused(self):
        fail = [page(status="parse_error", ids=())]
        report = assess_scan(scan(pages=fail, attempts=3), retry_budget=3)
        self.assertEqual(report["status"], "escalate")
        self.assertIn("escalate", report["next_action"])
        quota = assess_scan(scan(pages=[page(status="quota_paused", ids=())], attempts=3), retry_budget=3)
        self.assertEqual(quota["status"], "degraded")
        self.assertIn("quota", quota["next_action"])

    def test_strict_cursor_gap_cycle_and_terminal_rejection(self):
        bad = [[page(next_cursor="page:1"), page("page:2")],
               [page(next_cursor="page:0")],
               [page(), page("page:1")],
               [page(status="parse_error", ids=()), page("page:1")],
               [page(status="broken_link")],
               [page(status="quota_paused", ids=(), next_cursor="page:1")]]
        for pages in bad:
            with self.subTest(pages=pages), self.assertRaises(ReconciliationError):
                assess_scan(scan(pages=pages))

    def test_invalid_input_fails_closed(self):
        bad = [scan(synthetic=False), scan(source_id="https://invalid.example"),
               scan(mode="other"), scan(attempts=True), scan(pages=[]),
               scan(pages=[page(status="unknown")]),
               scan(pages=[page(ids=("record:a", "record:a"))]),
               scan(pages=[dict(page(), record_ids=["https://invalid.example"])]),
               scan(pages=[dict(page(), surplus=1)]),
               scan(mode="full", start_cursor=BASE + "page:1"),
               scan(pages=[page(next_cursor="page:0")])]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ReconciliationError):
                assess_scan(item)
        for budget in (-1, True, 21):
            with self.assertRaises(ReconciliationError):
                assess_scan(scan(), retry_budget=budget)

    def test_same_window_comparison_is_explicit_and_non_authoritative(self):
        complete = assess_scan(scan())
        inc = assess_scan(scan(mode="incremental"))
        self.assertEqual(compare_window(complete, inc)["outcome"], "matched")
        inc_other = assess_scan(scan(mode="incremental", pages=[page(ids=("record:b",))]))
        self.assertEqual(compare_window(complete, inc_other)["outcome"], "divergent")
        incomplete = assess_scan(scan(pages=[page(next_cursor="page:1")]))
        self.assertEqual(compare_window(incomplete, inc)["outcome"], "insufficient_coverage")
        with self.assertRaises(ReconciliationError):
            compare_window(complete, assess_scan(scan(mode="incremental", window_id=BASE + "window:two")))

    def test_purity_and_bounded_inputs(self):
        raw = scan(pages=[page(next_cursor="page:1"), page("page:1", ids=("record:b",))])
        saved = deepcopy(raw)
        self.assertEqual(assess_scan(raw), assess_scan(raw))
        self.assertEqual(raw, saved)
        with self.assertRaises(ReconciliationError):
            assess_scan(scan(pages=[page()] * 257))
        with self.assertRaises(ReconciliationError):
            assess_scan(scan(pages=[page(ids=tuple(f"record:{i}" for i in range(1001)))]))


if __name__ == "__main__":
    unittest.main()
