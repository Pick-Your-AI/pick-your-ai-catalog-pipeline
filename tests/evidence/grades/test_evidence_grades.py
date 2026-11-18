"""Adversarial synthetic-only evidence classification (no network)."""
import copy
import unittest

from src.evidence import EvidenceError, assess


def receipt(suffix="a", **overrides):
    value = {"receipt_id": f"synthetic:receipt-{suffix}", "lineage_id": "synthetic:source-a",
             "evidence_class": "Primary documentation", "review_state": "source_checked",
             "assessor_authority": "synthetic_checker", "supports_claim": True,
             "method_documented": False, "conditions_documented": False}
    value.update(overrides)
    return value


def assessment(kind="identity", scope=None, receipts=None):
    return {"schema_version": "0.1-draft", "synthetic": True, "publication_eligible": False,
            "claim_id": "synthetic:claim", "claim_type": kind,
            "scope": {} if scope is None else scope,
            "receipts": [] if receipts is None else receipts}


class EvidenceGradeTests(unittest.TestCase):
    def test_unknown_stays_unknown(self):
        result = assess(assessment())
        self.assertEqual(result["proposed_evidence_state"], "unknown")
        self.assertEqual(result["evidence_classes"], [])

    def test_source_checked_is_not_independent(self):
        result = assess(assessment(receipts=[receipt()]))
        self.assertEqual(result["proposed_evidence_state"], "source_checked")
        self.assertEqual(result["independent_reproduction_lineage_count"], 0)

    def test_reviewed_vendor_claim_remains_vendor_claim(self):
        value = receipt(evidence_class="Vendor claim", review_state="reviewed",
                        assessor_authority="synthetic_reviewer")
        result = assess(assessment(receipts=[value]))
        self.assertEqual(result["proposed_evidence_state"], "reviewed")
        self.assertEqual(result["evidence_classes"], ["Vendor claim"])

    def test_unverified_flags_do_not_upgrade(self):
        for authority in ("none", "synthetic_checker", "synthetic_reviewer"):
            with self.subTest(authority=authority):
                r = receipt(evidence_class="Independent measurement", review_state="independently_reproduced",
                            assessor_authority=authority, conditions_documented=True, method_documented=True)
                output = assess(assessment(receipts=[r]))
                self.assertNotEqual(output["proposed_evidence_state"], "independently_reproduced")
                self.assertIn("reproduction_unsubstantiated", output["warnings"])

    def test_independent_measurement_requires_method_and_conditions(self):
        for method, conditions in ((False, True), (True, False), (False, False)):
            with self.subTest(method=method, conditions=conditions):
                r = receipt(evidence_class="Independent measurement", review_state="independently_reproduced",
                            assessor_authority="synthetic_reproducer", method_documented=method,
                            conditions_documented=conditions)
                self.assertNotEqual(assess(assessment(receipts=[r]))["proposed_evidence_state"], "independently_reproduced")

    def test_reproduction_proposal_never_clears_rights_or_publication(self):
        r = receipt(evidence_class="Independent measurement", review_state="independently_reproduced",
                    assessor_authority="synthetic_reproducer", method_documented=True, conditions_documented=True)
        result = assess(assessment(receipts=[r]))
        self.assertEqual(result["proposed_evidence_state"], "independently_reproduced")
        self.assertEqual(result["independent_reproduction_lineage_count"], 1)
        self.assertFalse(result["publication_eligible"] or result["rights_cleared"] or result["assessment_authorized"])
        self.assertEqual(result["decision_status"], "synthetic_unverified")

    def test_derivative_citations_share_one_lineage(self):
        values = [receipt("a"), receipt("b", evidence_class="Estimate")]
        result = assess(assessment(receipts=values))
        self.assertEqual(result["supporting_lineage_count"], 1)
        self.assertIn("repeated_lineage_not_independent", result["warnings"])

    def test_reproduction_counts_unique_lineages_not_receipts(self):
        qualifying = {"evidence_class": "Independent measurement",
                      "review_state": "independently_reproduced",
                      "assessor_authority": "synthetic_reproducer",
                      "method_documented": True, "conditions_documented": True}
        same_lineage = [receipt("a", **qualifying), receipt("b", **qualifying)]
        result = assess(assessment(receipts=same_lineage))
        self.assertEqual(result["proposed_evidence_state"], "independently_reproduced")
        self.assertEqual(result["supporting_lineage_count"], 1)
        self.assertEqual(result["independent_reproduction_lineage_count"], 1)
        self.assertIn("repeated_lineage_not_independent", result["warnings"])
        distinct = same_lineage + [receipt("c", lineage_id="synthetic:source-b", **qualifying)]
        result = assess(assessment(receipts=distinct))
        self.assertEqual(result["supporting_lineage_count"], 2)
        self.assertEqual(result["independent_reproduction_lineage_count"], 2)
        self.assertFalse(result["publication_eligible"] or result["rights_cleared"]
                         or result["assessment_authorized"])

    def test_distinct_lineages_not_presumed_independently_measured(self):
        values = [receipt("a"), receipt("b", lineage_id="synthetic:source-b")]
        result = assess(assessment(receipts=values))
        self.assertEqual(result["supporting_lineage_count"], 2)
        self.assertEqual(result["proposed_evidence_state"], "source_checked")

    def test_unsupported_claim_excluded_from_grade(self):
        value = receipt(supports_claim=False, evidence_class="Vendor claim",
                        review_state="independently_reproduced", assessor_authority="synthetic_reproducer")
        self.assertEqual(assess(assessment(receipts=[value]))["proposed_evidence_state"], "unknown")

    def test_unqualified_universal_claims_not_graded(self):
        required = {"capability": ["version", "runtime"],
                    "benchmark": ["version", "runtime", "workload"],
                    "hardware_fit": ["version", "runtime", "hardware", "quantization"],
                    "price": ["version", "region", "currency"]}
        for kind, fields in required.items():
            for missing in fields:
                with self.subTest(kind=kind, missing=missing):
                    scope = {f: "synthetic" for f in fields if f != missing}
                    result = assess(assessment(kind, scope, [receipt()]))
                    self.assertEqual(result["proposed_evidence_state"], "unknown")
                    self.assertIn("scope_unqualified", result["warnings"])

    def test_scoped_benchmark_vendor_claim_not_reproduction(self):
        result = assess(assessment("benchmark", {"version": "v1", "runtime": "local", "workload": "prefill"},
                                   [receipt(evidence_class="Vendor claim", review_state="reviewed",
                                            assessor_authority="synthetic_reviewer")]))
        self.assertEqual(result["proposed_evidence_state"], "reviewed")
        self.assertEqual(result["independent_reproduction_lineage_count"], 0)

    def test_duplicate_receipt_id_fails_closed(self):
        with self.assertRaisesRegex(EvidenceError, "duplicate synthetic receipt identity"):
            assess(assessment(receipts=[receipt(), receipt()]))

    def test_extra_fields_and_non_synthetic_identifiers_rejected(self):
        for mutate in (lambda x: x.update({"publication_eligible": True}),
                       lambda x: x.update({"claim_id": "real:claim"}),
                       lambda x: x.update({"unexpected": "private"}),
                       lambda x: x["receipts"][0].update({"source_url": "private"}),
                       lambda x: x["receipts"][0].update({"lineage_id": "synthetic:lineage\n"}),
                       lambda x: x["receipts"][0].update({"assessor_authority": "actual_reviewer"})):
            x = assessment(receipts=[receipt()]); mutate(x)
            with self.assertRaisesRegex(EvidenceError, "invalid synthetic evidence assessment"):
                assess(x)

    def test_input_is_not_mutated(self):
        x = assessment(receipts=[receipt()]); previous = copy.deepcopy(x)
        assess(x)
        self.assertEqual(x, previous)

    def test_unknown_unreviewed_evidence_not_upgrade(self):
        result = assess(assessment(receipts=[receipt(review_state="unknown", assessor_authority="none")]))
        self.assertEqual(result["proposed_evidence_state"], "unknown")

    def test_schema_rejects_over_capacity_without_disclosing_values(self):
        x = assessment(receipts=[receipt(str(i), lineage_id=f"synthetic:source-{i}") for i in range(65)])
        with self.assertRaises(EvidenceError) as raised:
            assess(x)
        self.assertNotIn("source-64", str(raised.exception))
        self.assertEqual(str(raised.exception), "invalid synthetic evidence assessment")


if __name__ == "__main__":
    unittest.main()
