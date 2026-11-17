"""Synthetic wire-contract checks independent of schema construction."""
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from src.quarantine import GateFinding, append_attempt, as_document

ROOT = Path(__file__).resolve().parents[1]
GATE_CAUSES = (
    ("schema", "malformed"), ("identity", "identity_ambiguous"),
    ("evidence", "evidence_insufficient"), ("rights", "rights_unknown"),
    ("policy", "policy_denied"),
)


def document(statuses=("pass",) * 5):
    findings = tuple(GateFinding(gate, status,
        f"urn:pya:synthetic:wire:{gate}", cause if status != "pass" else None)
        for (gate, cause), status in zip(GATE_CAUSES, statuses))
    attempt = append_attempt((), candidate_id="urn:pya:synthetic:wire:candidate",
                             revision=1, findings=findings)[-1]
    return as_document(attempt)


class QuarantineSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((ROOT / "schemas/disposition.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def rejected(self, value):
        self.assertTrue(list(self.validator.iter_errors(value)))

    def test_all_243_gate_status_combinations_have_consistent_valid_wire_form(self):
        for statuses in product(("pass", "reject", "unknown"), repeat=5):
            with self.subTest(statuses=statuses):
                self.assertEqual(list(self.validator.iter_errors(document(statuses))), [])

    def test_missing_duplicate_extra_and_noncanonical_gate_coverage_is_rejected(self):
        valid = document()
        for values in (valid["evaluations"][:-1],
                       valid["evaluations"] + valid["evaluations"][:1],
                       [valid["evaluations"][0]] * 5,
                       list(reversed(valid["evaluations"]))):
            bad = deepcopy(valid)
            bad["evaluations"] = values
            with self.subTest(evaluations=values):
                self.rejected(bad)

    def test_failure_cause_must_match_its_gate_and_pass_must_have_none(self):
        for index, (_, expected) in enumerate(GATE_CAUSES):
            for _, wrong in GATE_CAUSES:
                if wrong == expected:
                    continue
                bad = document(("reject",) * 5)
                bad["evaluations"][index]["cause"] = wrong
                self.rejected(bad)
            bad = document(("unknown",) * 5)
            del bad["evaluations"][index]["cause"]
            self.rejected(bad)
            bad = document()
            bad["evaluations"][index]["cause"] = expected
            self.rejected(bad)

    def test_rejected_rights_cannot_claim_review_pending_or_hide_diagnostics(self):
        valid = document(("pass", "pass", "pass", "reject", "pass"))
        for field, value in (("state", "needs_independent_review"),
                             ("causes", []), ("next_actions", []),
                             ("causes", ["malformed"]),
                             ("next_actions", ["correct_and_retry"])):
            bad = deepcopy(valid)
            bad[field] = value
            with self.subTest(field=field, value=value):
                self.rejected(bad)

    def test_causes_and_actions_are_exact_sets_of_nonpassing_gates(self):
        for field in ("causes", "next_actions"):
            full = document(("reject",) * 5)
            for index in range(5):
                bad = deepcopy(full)
                del bad[field][index]
                self.rejected(bad)
                bad = document()
                bad[field] = [full[field][index]]
                self.rejected(bad)
            bad = deepcopy(full)
            bad[field].append(bad[field][0])
            self.rejected(bad)
        bad = document()
        bad["state"] = "quarantined"
        self.rejected(bad)

    def test_synthetic_identity_and_scalar_boundaries_are_enforced(self):
        for field, value in (("synthetic", False), ("synthetic", 1),
                             ("candidate_id", "urn:pya:real:wire:candidate"),
                             ("candidate_id", "urn:pya:synthetic:item\n"),
                             ("candidate_id", "urn:pya:synthetic:" + "a" * 256),
                             ("revision", True), ("revision", 0),
                             ("attempt", True), ("attempt", 0), ("attempt", 33),
                             ("state", "published")):
            bad = document()
            bad[field] = value
            with self.subTest(field=field, value=value):
                self.rejected(bad)
        for suffix in ("\n", "\r", "\r\n"):
            bad = document()
            bad["evaluations"][0]["evaluation_id"] += suffix
            self.rejected(bad)

    def test_undeclared_wire_fields_are_rejected(self):
        bad = document()
        bad["publication_authorized"] = True
        self.rejected(bad)
        bad = document()
        bad["evaluations"][0]["publication_authorized"] = True
        self.rejected(bad)


if __name__ == "__main__":
    unittest.main()
