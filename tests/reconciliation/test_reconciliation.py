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


class HostileDict(dict):
    def keys(self):
        raise AssertionError("untrusted keys method executed")

    def __getitem__(self, key):
        raise AssertionError("untrusted lookup executed")


class HostileList(list):
    def __iter__(self):
        raise AssertionError("untrusted iteration executed")

    def __len__(self):
        raise AssertionError("untrusted length executed")


class HostileString(str):
    def __eq__(self, other):
        raise AssertionError("untrusted equality executed")

    def __hash__(self):
        raise AssertionError("untrusted hashing executed")


class ReportBoundaryTests(unittest.TestCase):
    def reports(self):
        return assess_scan(scan()), assess_scan(scan(mode="incremental"))

    def test_missing_or_extra_fields_rejected_in_both_reports(self):
        for index in (0, 1):
            for field in self.reports()[index]:
                reports = self.reports()
                del reports[index][field]
                with self.subTest(index=index, missing=field), self.assertRaises(ReconciliationError):
                    compare_window(*reports)
            reports = self.reports()
            reports[index]["unexpected"] = True
            with self.assertRaises(ReconciliationError):
                compare_window(*reports)

    def test_report_types_and_id_bounds_rejected_in_both_roles(self):
        changes = {
            "schema_version": [None, HostileString("reconciliation-draft-0.1.0")],
            "mode": [None, HostileString("full")],
            "source_id": [None, "https://invalid.example", BASE + "a" * 257],
            "scan_id": [None, HostileString(BASE + "scan:one")],
            "window_id": [False, "real:window"],
            "status": [None, HostileString("complete")],
            "next_action": [None, HostileString("retain_observations_for_independent_review")],
            "window_complete": ["false", 1, None],
            "full_coverage_claimed": ["false", 0, None],
            "pages_seen": [True, 0, 257, 1.0],
            "record_count": [True, -1, 2, 1001, 1.0],
            "record_ids": [None, (), HostileList(), [None], [["unhashable"]],
                           [BASE + "record:a"] * 2, ["real:record"],
                           [HostileString(BASE + "record:a")],
                           [BASE + f"record:{i}" for i in range(1001)]],
            "failure": ["ok", [], HostileString("parse_error")],
            "resume_cursor": [False, HostileString(BASE + "page:one")],
            "prior_count_changed": [0, "false", []],
        }
        for field in ("synthetic", "publication_eligible", "deletion_inferred",
                      "withdrawal_inferred", "last_known_preserved"):
            changes[field] = [None, 0, 1, "false"]
        for index in (0, 1):
            for field, values in changes.items():
                for case, value in enumerate(values):
                    reports = self.reports()
                    reports[index][field] = value
                    with self.subTest(index=index, field=field, case=case), self.assertRaises(ReconciliationError):
                        compare_window(*reports)

    def test_python_container_subclasses_are_rejected_before_methods_run(self):
        full, inc = self.reports()
        for reports in ((HostileDict(full), inc), (full, HostileDict(inc))):
            with self.assertRaises(ReconciliationError):
                compare_window(*reports)
        bad_scans = [HostileDict(scan()), scan(pages=HostileList([page()])),
                     scan(pages=[HostileDict(page())]), scan(pages=[page(ids=())])]
        bad_scans[-1]["pages"][0]["record_ids"] = HostileList()
        bad_scans += [scan(mode=HostileString("full")),
                      scan(schema_version=HostileString("reconciliation-draft-0.1.0")),
                      scan(source_id=HostileString(BASE + "source:fictional")),
                      scan(pages=[page(status=HostileString("ok"))]),
                      scan(pages=[dict(page(), record_ids=[HostileString(BASE + "record:a")])])]
        for index, value in enumerate(bad_scans):
            with self.subTest(index=index), self.assertRaises(ReconciliationError):
                assess_scan(value)
        class StringKey(str):
            pass
        for raw, operation in ((scan(), assess_scan), (full, lambda r: compare_window(r, inc))):
            raw[StringKey("source_id")] = raw.pop("source_id")
            with self.assertRaises(ReconciliationError):
                operation(raw)

    def test_contradictory_state_and_scope_rejected(self):
        full, inc = self.reports()
        degraded = assess_scan(scan(mode="incremental", pages=[page(next_cursor="page:1"),
                                  page("page:1", status="transport_error", ids=())]))
        cases = [(full, {"status": "degraded"}), (full, {"failure": "parse_error"}),
                 (full, {"resume_cursor": BASE + "page:1"}),
                 (full, {"full_coverage_claimed": False}),
                 (inc, {"full_coverage_claimed": True}),
                 (inc, {"prior_count_changed": False}),
                 (degraded, {"window_complete": "false"}),
                 (degraded, {"window_complete": True}),
                 (degraded, {"status": "complete"}),
                 (degraded, {"resume_cursor": None}),
                 (degraded, {"next_action": "retain_observations_for_independent_review"}),
                 (degraded, {"prior_count_changed": True}),
                 (degraded, {"pages_seen": 1}),
                 (degraded, {"failure": "quota_paused", "status": "escalate"})]
        for original, changes in cases:
            report = dict(original, **changes)
            reports = (report, inc) if report["mode"] == "full" else (full, report)
            with self.subTest(changes=changes), self.assertRaises(ReconciliationError):
                compare_window(*reports)
        for field in ("source_id", "window_id"):
            other = dict(inc, **{field: BASE + "different:scope"})
            with self.assertRaises(ReconciliationError):
                compare_window(full, other)
        with self.assertRaises(ReconciliationError):
            compare_window(inc, full)

    def test_healthy_batches_compare_observations_independent_of_page_boundaries(self):
        full = assess_scan(scan(pages=[page(next_cursor="page:1", ids=("record:b", "record:a")),
                                      page("page:1", ids=("record:b", "record:c"))]),
                           prior_complete_count=3)
        inc = assess_scan(scan(mode="incremental", start_cursor=BASE + "page:delta",
                              pages=[page("page:delta", ids=("record:c", "record:a", "record:b"))]))
        inc["record_ids"].reverse()
        saved = deepcopy((full, inc))
        self.assertEqual(compare_window(full, inc)["outcome"], "matched")
        self.assertFalse(compare_window(full, inc)["requires_review"])
        self.assertEqual((full, inc), saved)
        inc["record_ids"].pop()
        inc["record_count"] -= 1
        result = compare_window(full, inc)
        self.assertEqual(result["outcome"], "divergent")
        self.assertTrue(result["requires_review"])

    def test_all_valid_incomplete_states_require_review_even_with_matching_ids(self):
        full = assess_scan(scan())
        fixtures = [scan(mode="incremental", pages=[page(next_cursor="page:1")])]
        for failure in ("parse_error", "broken_link", "quota_paused", "transport_error"):
            for attempts in (0, 3):
                fixtures.append(scan(mode="incremental", attempts=attempts,
                                     pages=[page(next_cursor="page:1"),
                                            page("page:1", status=failure, ids=())]))
        for fixture in fixtures:
            inc = assess_scan(fixture)
            self.assertEqual(full["record_ids"], inc["record_ids"])
            result = compare_window(full, inc)
            self.assertEqual(result["outcome"], "insufficient_coverage")
            self.assertTrue(result["requires_review"])
            self.assertFalse(result["publication_eligible"])
            self.assertFalse(result["deletion_inferred"])


if __name__ == "__main__":
    unittest.main()
