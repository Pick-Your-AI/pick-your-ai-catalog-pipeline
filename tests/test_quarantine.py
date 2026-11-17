"""Offline rejection, re-entry and mixed-batch tests using synthetic identities."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from src.quarantine import (GATES, GateFinding, QuarantineError,
                            append_attempt, as_document, evaluate_batch)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "urn:pya:synthetic:candidate:one"
CASES = {
    "schema": "malformed", "identity": "identity_ambiguous",
    "evidence": "evidence_insufficient", "rights": "rights_unknown",
    "policy": "policy_denied",
}


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
                         tuple(GateFinding(f.gate, f.status, "urn:pya:real:evaluation", f.cause) for f in valid)]
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


if __name__ == "__main__":
    unittest.main()
