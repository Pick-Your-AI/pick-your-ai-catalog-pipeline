"""Offline rejection, re-entry and mixed-batch tests using synthetic identities."""
import json
from dataclasses import replace
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from src.quarantine import (GATES, MAX_ATTEMPTS, MAX_BATCH, Attempt,
                            GateFinding, QuarantineError,
                            append_attempt, as_document, evaluate_batch)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "urn:pya:synthetic:candidate:one"
CASES = {
    "schema": "malformed", "identity": "identity_ambiguous",
    "evidence": "evidence_insufficient", "rights": "rights_unknown",
    "policy": "policy_denied",
}


class UnsafeString(str):
    """A nonexact scalar must never reach comparison or hashing."""
    def __eq__(self, other):
        raise AssertionError("Unvalidated scalar equality")

    def __hash__(self):
        raise AssertionError("Unvalidated scalar hashing")


class UnhashableString(str):
    __hash__ = None


class UnsafeInt(int):
    def __le__(self, other):
        raise AssertionError("Unvalidated integer comparison")

    def __lt__(self, other):
        raise AssertionError("Unvalidated integer comparison")


class UnsafeTuple(tuple):
    def __len__(self):
        raise AssertionError("Unvalidated tuple length")

    def __iter__(self):
        raise AssertionError("Unvalidated tuple iteration")


def checks(revision, failed=()):
    return tuple(GateFinding(g, "reject" if g in failed else "pass",
                             f"urn:pya:synthetic:evaluation:{revision}:{g}",
                             CASES[g] if g in failed else None) for g in GATES)


class QuarantineTest(unittest.TestCase):
    def attempt(self, history=(), revision=1, failed=("rights",), candidate=CANDIDATE):
        return append_attempt(history, candidate_id=candidate, revision=revision,
                              findings=checks(revision, failed))

    def test_all_failures_preserve_machine_readable_causes_and_actions(self):
        history = self.attempt(failed=GATES)
        item = history[-1]
        self.assertEqual(item.state, "quarantined")
        self.assertEqual(set(item.causes), set(CASES.values()))
        self.assertEqual(len(item.next_actions), 5)
        self.assertNotIn("release", as_document(item))
        schema = json.loads((ROOT / "schemas/disposition.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(as_document(item))), [])

    def test_no_failures_only_request_review_without_publication_authority(self):
        item = self.attempt(failed=())[-1]
        self.assertEqual((item.state, item.causes, item.next_actions),
                         ("needs_independent_review", (), ()))
        self.assertEqual(as_document(item)["synthetic"], True)

    def test_retry_retains_old_failure_and_rechecks_every_gate(self):
        first = self.attempt(failed=("rights", "evidence"))
        second = self.attempt(first, revision=2, failed=("policy",))
        self.assertIs(second[0], first[0])
        self.assertEqual(first[0].causes, ("evidence_insufficient", "rights_unknown"))
        self.assertEqual(second[1].causes, ("policy_denied",))
        third = self.attempt(second, revision=3, failed=())
        self.assertEqual(third[-1].state, "needs_independent_review")
        self.assertEqual(len(third), 3)
        self.assertEqual(third[0], first[0])

    def test_no_stale_gate_or_partial_success_reuse(self):
        first = self.attempt()
        with self.assertRaises(QuarantineError):
            append_attempt(first, candidate_id=CANDIDATE, revision=2, findings=checks(1))
        with self.assertRaises(QuarantineError):
            append_attempt(first, candidate_id=CANDIDATE, revision=2, findings=checks(2)[:4])
        with self.assertRaises(QuarantineError):
            self.attempt(first, revision=1)
        with self.assertRaises(QuarantineError):
            self.attempt(first, revision=True)

    def test_invalid_gate_shapes_do_not_grant_review_pending(self):
        valid = checks(1)
        invalid_cases = [valid[:-1], valid + valid[:1], valid[:1] + valid[:1] + valid[2:],
                         valid[:1] + (GateFinding("rights", "pass", valid[1].evaluation_id),) + valid[2:],
                         tuple(GateFinding(f.gate, "unknown", f.evaluation_id) for f in valid),
                         tuple(GateFinding(f.gate, "pass", f.evaluation_id, "malformed") for f in valid),
                         tuple(GateFinding(f.gate, f.status, "urn:pya:real:evaluation", f.cause) for f in valid),
                         tuple(GateFinding(f.gate, "reject", f.evaluation_id, {}) for f in valid),
                         tuple(GateFinding([], f.status, f.evaluation_id, f.cause) for f in valid)]
        for bad in invalid_cases:
            with self.subTest(bad=bad), self.assertRaises(QuarantineError):
                append_attempt((), candidate_id=CANDIDATE, revision=1, findings=bad)

    def test_history_forgery_is_rejected_where_internal_consistency_fails(self):
        first = self.attempt()
        tampered = (first[0].__class__(first[0].candidate_id, 1, 1,
                                     "needs_independent_review", (), (), first[0].findings),)
        with self.assertRaises(QuarantineError):
            self.attempt(tampered, revision=2)
        with self.assertRaises(QuarantineError):
            self.attempt(first, revision=2, candidate="urn:pya:synthetic:candidate:other")

    def test_batch_does_not_suppress_healthy_diagnostics(self):
        other = "urn:pya:synthetic:candidate:two"
        output = evaluate_batch(((CANDIDATE, 1, (), checks(1, ("schema",))),
                                 (other, 1, (), checks(2, ("rights",))),
                                 ("urn:pya:real:invalid", 1, (), checks(3)),
                                 (CANDIDATE, 1, (), checks(4))))
        self.assertEqual([r[2] for r in output],
                         [None, None, "invalid_candidate_id", "duplicate_candidate_id"])
        self.assertEqual(output[0][1][0].causes, ("malformed",))
        self.assertEqual(output[1][1][0].causes, ("rights_unknown",))
        self.assertEqual(len(output[0][1]), 1)
        with self.assertRaises(QuarantineError):
            evaluate_batch([])

    def test_synthetic_gate_id_and_candidate_are_not_optional(self):
        for candidate in (None, "urn:pya:real:item", "", "urn:pya:synthetic:bad id"):
            with self.subTest(candidate=candidate), self.assertRaises(QuarantineError):
                self.attempt(candidate=candidate)
        with self.assertRaises(QuarantineError):
            self.attempt(revision=0)

    def assert_rejected_attempt(self, entry):
        # Serialization and use as prior history must enforce the same boundary.
        with self.assertRaises(QuarantineError):
            as_document(entry)
        with self.assertRaises(QuarantineError):
            self.attempt((entry,), revision=2)

    def test_serializer_rejects_forged_synthetic_marker_and_derived_metadata(self):
        entry = self.attempt()[-1]
        for change in (
                {"candidate_id": "urn:pya:real:candidate"},
                {"candidate_id": "urn:pya:synthetic:" + "a" * 256},
                {"revision": 0}, {"revision": True},
                {"number": 0}, {"number": MAX_ATTEMPTS + 1}, {"number": True},
                {"state": "released"}, {"state": "needs_independent_review"},
                {"causes": ()}, {"causes": ("policy_denied",)},
                {"causes": ("rights_unknown",) * 6},
                {"next_actions": ()}, {"next_actions": ("correct_and_retry",)},
                {"next_actions": ("request_rights_review",) * 6},
                {"findings": ()}, {"findings": entry.findings * 2},
                {"findings": tuple(reversed(entry.findings))}):
            with self.subTest(change=list(change)):
                self.assert_rejected_attempt(replace(entry, **change))
        self.assertEqual(as_document(entry)["state"], "quarantined")
        passing = self.attempt(failed=())[-1]
        self.assert_rejected_attempt(replace(passing, state="quarantined"))

    def test_nonexact_finding_fields_are_rejected_before_equality_or_hashing(self):
        valid = checks(1)
        first = valid[0]
        invalid_first = (
            replace(first, gate=UnhashableString("schema")),
            replace(first, gate=UnsafeString("schema")),
            replace(first, gate=[]),
            replace(first, status=UnsafeString("pass")),
            replace(first, evaluation_id=UnsafeString(first.evaluation_id)),
            replace(first, status="reject", cause=UnsafeString("malformed")),
            replace(first, status="reject", cause=[]),
        )
        for index, finding in enumerate(invalid_first):
            with self.subTest(index=index), self.assertRaises(QuarantineError):
                append_attempt((), candidate_id=CANDIDATE, revision=1,
                               findings=(finding,) + valid[1:])

    def test_nonexact_attempt_fields_and_containers_cannot_bypass_validation(self):
        entry = self.attempt()[-1]
        for change in (
                {"candidate_id": UnsafeString(CANDIDATE)},
                {"revision": UnsafeInt(1)}, {"number": UnsafeInt(1)},
                {"state": UnsafeString("quarantined")},
                {"causes": (UnsafeString("rights_unknown"),)},
                {"next_actions": (UnsafeString("request_rights_review"),)},
                {"causes": ["rights_unknown"]},
                {"next_actions": ["request_rights_review"]},
                {"causes": UnsafeTuple(entry.causes)},
                {"next_actions": UnsafeTuple(entry.next_actions)},
                {"findings": UnsafeTuple(entry.findings)},
                {"findings": list(entry.findings)}):
            with self.subTest(change=list(change)):
                self.assert_rejected_attempt(replace(entry, **change))
        with self.assertRaises(QuarantineError):
            self.attempt(UnsafeTuple((entry,)), revision=2)
        with self.assertRaises(QuarantineError):
            self.attempt(revision=UnsafeInt(1))
        with self.assertRaises(QuarantineError):
            self.attempt(candidate=UnsafeString(CANDIDATE))

    def test_incomplete_or_subclassed_records_are_rejected(self):
        class AttemptSubclass(Attempt):
            pass

        class FindingSubclass(GateFinding):
            pass

        entry = self.attempt()[-1]
        for invalid in (Attempt.__new__(Attempt),
                        AttemptSubclass(entry.candidate_id, entry.revision,
                                        entry.number, entry.state, entry.causes,
                                        entry.next_actions, entry.findings)):
            self.assert_rejected_attempt(invalid)
        for invalid in (GateFinding.__new__(GateFinding),
                        FindingSubclass("schema", "pass", checks(1)[0].evaluation_id)):
            findings = (invalid,) + entry.findings[1:]
            with self.assertRaises(QuarantineError):
                append_attempt((), candidate_id=CANDIDATE, revision=1,
                               findings=findings)
            self.assert_rejected_attempt(replace(entry, findings=findings))

    def test_evaluation_ids_are_unique_within_attempt_and_across_supplied_history(self):
        first = self.attempt(failed=())
        duplicated = tuple(replace(f, evaluation_id=first[0].findings[0].evaluation_id)
                           for f in first[0].findings)
        self.assert_rejected_attempt(replace(first[0], findings=duplicated))
        second = self.attempt(first, revision=2, failed=())
        # Reusing even one ID for another gate is forbidden across attempts.
        reused = (replace(second[-1].findings[0],
                          evaluation_id=first[0].findings[-1].evaluation_id),
                  ) + second[-1].findings[1:]
        with self.assertRaises(QuarantineError):
            append_attempt(first, candidate_id=CANDIDATE, revision=2,
                           findings=reused)
        forged_second = replace(second[-1], findings=reused)
        with self.assertRaises(QuarantineError):
            self.attempt((first[0], forged_second), revision=3)

    def test_batch_continues_after_nonexact_findings_and_malformed_history(self):
        entries = []
        valid = checks(1)
        malformed_findings = ((replace(valid[0], gate=UnhashableString("schema")),)
                              + valid[1:])
        malformed_history = (replace(self.attempt()[-1],
                                     state=UnsafeString("quarantined")),)
        for index, (history, findings) in enumerate((
                ((), malformed_findings), (malformed_history, checks(2)),
                ((), (GateFinding.__new__(GateFinding),) + valid[1:]))):
            entries.append((f"urn:pya:synthetic:batch:{index}", 2,
                            history, findings))
        entries.append(("urn:pya:synthetic:batch:healthy", 1, (),
                        checks(4, ("rights",))))
        output = evaluate_batch(tuple(entries))
        self.assertEqual([item[2] for item in output],
                         ["invalid_attempt", "invalid_attempt", "invalid_attempt", None])
        self.assertEqual(as_document(output[-1][1][-1])["causes"], ["rights_unknown"])

    def test_attempt_and_batch_limits_remain_enforced(self):
        history = ()
        for revision in range(1, MAX_ATTEMPTS + 1):
            history = self.attempt(history, revision=revision)
        self.assertEqual(as_document(history[-1])["attempt"], MAX_ATTEMPTS)
        with self.assertRaises(QuarantineError):
            self.attempt(history, revision=MAX_ATTEMPTS + 1)
        self.assert_rejected_attempt(replace(history[0], number=MAX_ATTEMPTS + 1))
        with self.assertRaises(QuarantineError):
            evaluate_batch((None,) * (MAX_BATCH + 1))
        self.assertEqual(len(evaluate_batch((None,) * MAX_BATCH)), MAX_BATCH)
        with self.assertRaises(QuarantineError):
            evaluate_batch(UnsafeTuple(()))

    def test_new_input_normalizes_gates_but_stored_attempts_require_canonical_order(self):
        history = append_attempt((), candidate_id=CANDIDATE, revision=1,
                                 findings=tuple(reversed(checks(1, ("schema", "policy")))))
        document = as_document(history[-1])
        self.assertEqual(tuple(item["gate"] for item in document["evaluations"]), GATES)
        self.assertEqual(document["causes"], ["malformed", "policy_denied"])
        self.assert_rejected_attempt(replace(history[-1],
                                             findings=tuple(reversed(history[-1].findings))))

    def test_serializer_returns_independent_mutable_document(self):
        entry = self.attempt()[-1]
        document = as_document(entry)
        document["evaluations"][0]["evaluation_id"] = "urn:pya:real:forged"
        document["causes"].clear()
        document["next_actions"].append("publish")
        fresh = as_document(entry)
        self.assertEqual(fresh["causes"], ["rights_unknown"])
        self.assertEqual(fresh["next_actions"], ["request_rights_review"])
        self.assertEqual(fresh["evaluations"][0]["evaluation_id"], checks(1)[0].evaluation_id)


if __name__ == "__main__":
    unittest.main()
