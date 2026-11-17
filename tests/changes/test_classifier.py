"""Offline negative and priority tests for source change classification."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.changes import ChangeError, classify  # noqa: E402


def observation(tag="before"):
    return {
        "schema_version": "change-set-draft-0.1.0",
        "synthetic": True,
        "source_id": "urn:pya:synthetic:source:fixture",
        "material_id": "urn:pya:synthetic:material:fixture",
        "observation_id": f"urn:pya:synthetic:observation:{tag}",
        "captured_at": "2026-11-17T00:00:00Z" if tag == "before" else "2026-11-17T01:00:00Z",
        "content_sha256": "a" * 64,
        "parser_revision": "fixture-parser-v1",
        "claims": [{"path": "model.alias", "kind": "identity", "value": "model-a", "evidence_ref": "urn:pya:synthetic:evidence:a"}]
    }


def pair():
    return observation(), observation("after")


class ChangeClassifierTests(unittest.TestCase):
    def test_unchanged_revisions_retained_with_no_publication(self):
        before, after = pair()
        result = classify(before, after)
        self.assertEqual(result["decision"], "unchanged")
        self.assertFalse(result["requires_review"])
        self.assertFalse(result["publication_eligible"])
        self.assertEqual(result["previous"]["observation_id"], before["observation_id"])
        self.assertEqual(result["current"]["observation_id"], after["observation_id"])

    def test_byte_only_change_not_mistaken_for_safe_cosmetic_release(self):
        before, after = pair()
        after["content_sha256"] = "b" * 64
        result = classify(before, after)
        self.assertEqual(result["decision"], "byte_only_review")
        self.assertEqual(result["cause_flags"], ["raw_bytes_changed"])
        self.assertTrue(result["requires_review"])
        self.assertFalse(result["changes"])

    def test_parser_revision_requires_explicit_review_even_same_claims(self):
        before, after = pair()
        after["parser_revision"] = "fixture-parser-v2"
        self.assertEqual(classify(before, after)["decision"], "parser_review")
        after["content_sha256"] = "b" * 64
        self.assertEqual(classify(before, after)["cause_flags"],
                         ["raw_bytes_changed", "parser_revision_changed"])

    def test_alias_retargeting_remains_critical_and_both_values_survive(self):
        before, after = pair()
        after["claims"][0]["value"] = "model-b"
        result = classify(before, after)
        self.assertEqual(result["decision"], "semantic_review")
        self.assertEqual(result["changes"][0]["priority"], "critical")
        self.assertEqual(result["changes"][0]["before"]["value"], "model-a")
        self.assertEqual(result["changes"][0]["after"]["value"], "model-b")
        self.assertIn("same_bytes_claim_conflict", result["cause_flags"])

    def test_model_retirement_or_availability_remains_unverified(self):
        before, after = pair()
        before["claims"][0].update(path="model.availability", kind="availability", value="listed")
        after["claims"][0].update(path="model.availability", kind="availability", value="retired")
        result = classify(before, after)
        self.assertEqual(result["changes"][0]["review_route"], "availability_or_retirement_review")
        self.assertEqual(result["decision"], "semantic_review")
        self.assertFalse(result["publication_eligible"])

    def test_price_meter_and_currency_changes_are_critical(self):
        before, after = pair()
        for obs in (before, after):
            obs["claims"][0].update(path="price.input", kind="price", value="1.25", unit="per_1m_tokens", currency="USD")
        after["claims"][0]["unit"] = "per_1k_tokens"
        self.assertEqual(classify(before, after)["changes"][0]["review_route"], "price_meter_or_currency_review")
        after["claims"][0].update(unit="per_1m_tokens", currency="EUR")
        self.assertEqual(classify(before, after)["changes"][0]["priority"], "critical")
        after["claims"][0].update(currency="USD", value="1.50")
        self.assertEqual(classify(before, after)["changes"][0]["review_route"], "price_value_review")

    def test_license_and_rights_changes_take_hold_precedence(self):
        before, after = pair()
        for obs in (before, after):
            obs["claims"].append({"path": "source.license", "kind": "license", "value": "unknown", "evidence_ref": "urn:pya:synthetic:evidence:license"})
        after["claims"][-1]["value"] = "unreviewed-new-terms"
        after["claims"][0]["value"] = "model-b"
        result = classify(before, after)
        self.assertEqual(result["decision"], "rights_hold")
        self.assertEqual(result["changes"][1]["priority"], "hold")
        self.assertIn("source_rights_review", result["changes"][1]["review_route"])
        before["claims"][-1]["kind"] = after["claims"][-1]["kind"] = "rights"
        self.assertEqual(classify(before, after)["decision"], "rights_hold")

    def test_evidence_only_changes_remain_material(self):
        before, after = pair()
        after["claims"][0]["evidence_ref"] = "urn:pya:synthetic:evidence:new"
        result = classify(before, after)
        self.assertEqual(result["changes"][0]["review_route"], "identity_or_claim_kind_review")
        self.assertEqual(result["decision"], "semantic_review")

    def test_generic_unknowns_are_visible_not_discarded(self):
        before, after = pair()
        for obs in (before, after):
            obs["claims"][0]["kind"] = "other"
        after["claims"][0]["value"] = "new"
        result = classify(before, after)
        self.assertEqual(result["changes"][0]["priority"], "review")
        self.assertIn("other", result["impact_classes"])

    def test_added_and_removed_claims_do_not_mean_source_deletion(self):
        before, after = pair()
        after["claims"] = []
        result = classify(before, after)
        self.assertEqual(result["changes"][0]["after"], None)
        self.assertEqual(result["decision"], "semantic_review")
        self.assertEqual(result["previous"]["claims"], before["claims"])

    def test_cross_source_cross_material_and_identity_reuse_fail(self):
        before, after = pair()
        for key in ("source_id", "material_id"):
            mismatched = deepcopy(after)
            mismatched[key] = "urn:pya:synthetic:other:source"
            with self.assertRaises(ChangeError):
                classify(before, mismatched)
        after["observation_id"] = before["observation_id"]
        with self.assertRaises(ChangeError):
            classify(before, after)

    def test_reversed_and_invalid_timestamps_fail(self):
        before, after = pair()
        after["captured_at"] = "2026-11-16T23:59:59Z"
        with self.assertRaises(ChangeError):
            classify(before, after)
        after["captured_at"] = "2026-11-17T01:00:00+01:00"
        with self.assertRaises(ChangeError):
            classify(before, after)
        after["captured_at"] = "2026-13-17T01:00:00Z"
        with self.assertRaises(ChangeError):
            classify(before, after)

    def test_synthetic_production_rejection(self):
        before, after = pair()
        for invalid in (False, "true", 1):
            after["synthetic"] = invalid
            with self.assertRaises(ChangeError):
                classify(before, after)

    def test_invalid_price_floats_nonfinite_and_undeclared_units_fail(self):
        before, after = pair()
        for obs in (before, after):
            obs["claims"][0].update(kind="price", value="12.00", currency="USD", unit="per_1m_tokens")
        for bad in (1.0, float("nan"), "1e4", "01.2", "+2"):
            after["claims"][0]["value"] = bad
            with self.assertRaises(ChangeError):
                classify(before, after)
        after["claims"][0].update(value="12.00", unknown_unit="a")
        with self.assertRaises(ChangeError):
            classify(before, after)

    def test_duplicate_paths_unknown_kind_and_extra_metadata_fail(self):
        before, after = pair()
        before["claims"].append(deepcopy(before["claims"][0]))
        with self.assertRaises(ChangeError):
            classify(before, after)
        before["claims"].pop()
        after["claims"][0]["kind"] = "guess"
        with self.assertRaises(ChangeError):
            classify(before, after)
        after["claims"][0]["kind"] = "identity"
        after["secret"] = "must-not-be-accepted"
        with self.assertRaises(ChangeError):
            classify(before, after)

    def test_input_dictionaries_are_never_mutated_and_results_are_copies(self):
        before, after = pair()
        original_before, original_after = deepcopy(before), deepcopy(after)
        result = classify(before, after)
        result["previous"]["claims"][0]["value"] = "corrupt"
        self.assertEqual(before, original_before)
        self.assertEqual(after, original_after)

    def test_schema_rejects_publication_and_unknown_result_field(self):
        before, after = pair()
        result = classify(before, after)
        schema = json.loads((ROOT / "schemas/change-set.schema.json").read_text())
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(result)), [])
        result["publication_eligible"] = True
        self.assertTrue(list(validator.iter_errors(result)))
        result["publication_eligible"] = False
        result["private_info"] = "test"
        self.assertTrue(list(validator.iter_errors(result)))


if __name__ == "__main__":
    unittest.main()
