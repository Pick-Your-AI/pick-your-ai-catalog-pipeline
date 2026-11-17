"""Offline negative and priority tests for source change classification."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.changes import ChangeError, _timestamp, classify  # noqa: E402


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
        for kind in ("identity", "price", "availability", "evidence", "other"):
            with self.subTest(kind=kind):
                before, after = pair()
                for obs in (before, after):
                    obs["claims"][0]["kind"] = kind
                    if kind == "price":
                        obs["claims"][0].update(value="1.25", unit="per_token", currency="USD")
                after["claims"][0]["evidence_ref"] = "urn:pya:synthetic:evidence:new"
                result = classify(before, after)
                self.assertEqual(set(result["impact_classes"]), {kind, "evidence"})
                self.assertEqual(result["changes"][0]["priority"], "review")
                self.assertEqual(result["changes"][0]["review_route"], "evidence_lineage_review")
                self.assertEqual(result["changes"][0]["review_requirements"], ["evidence_lineage_review"])
                self.assertEqual(result["decision"], "semantic_review")
                self.assertTrue(result["requires_review"])
                self.assertEqual(result["previous"], before)
                self.assertEqual(result["current"], after)
                self.assertFalse(result["publication_eligible"])

    def test_mixed_identity_and_evidence_changes_require_both_reviews(self):
        before, after = pair()
        after["claims"][0].update(value="model-b", evidence_ref="urn:pya:synthetic:evidence:new")
        result = classify(before, after)
        self.assertEqual(result["impact_classes"], ["evidence", "identity"])
        self.assertEqual(result["changes"][0]["priority"], "critical")
        self.assertEqual(result["changes"][0]["review_route"], "identity_or_claim_kind_review")
        self.assertEqual(result["changes"][0]["review_requirements"],
                         ["identity_or_claim_kind_review", "evidence_lineage_review"])
        self.assertEqual(result["decision"], "semantic_review")

    def test_evidence_changes_never_override_rights_or_license_hold(self):
        for kind in ("rights", "license"):
            for semantic_change in (False, True):
                with self.subTest(kind=kind, semantic_change=semantic_change):
                    before, after = pair()
                    for obs in (before, after):
                        obs["claims"][0].update(kind=kind, value="unknown")
                    after["claims"][0]["evidence_ref"] = "urn:pya:synthetic:evidence:new"
                    if semantic_change:
                        after["claims"][0]["value"] = "unreviewed-new-terms"
                    result = classify(before, after)
                    self.assertEqual(set(result["impact_classes"]), {kind, "evidence"})
                    self.assertEqual(result["changes"][0]["priority"], "hold")
                    self.assertEqual(result["changes"][0]["review_route"], "source_rights_review_before_any_operation")
                    self.assertEqual(result["changes"][0]["review_requirements"],
                                     ["source_rights_review_before_any_operation", "evidence_lineage_review"])
                    self.assertEqual(result["decision"], "rights_hold")
                    self.assertEqual(result["next_action"], "pause_source_operations_and_request_exact_rights_decision")
                    self.assertFalse(result["publication_eligible"])

    def test_adding_or_removing_claims_preserves_evidence_review(self):
        for added in (False, True):
            with self.subTest(added=added):
                before, after = pair()
                (before if added else after)["claims"] = []
                result = classify(before, after)
                self.assertEqual(result["impact_classes"], ["evidence", "identity"])
                self.assertIn("evidence_lineage_review", result["changes"][0]["review_requirements"])

    def test_identity_value_change_does_not_invent_evidence_change(self):
        before, after = pair()
        after["claims"][0]["value"] = "model-b"
        result = classify(before, after)
        self.assertEqual(result["impact_classes"], ["identity"])
        self.assertEqual(result["changes"][0]["review_requirements"], ["identity_or_claim_kind_review"])

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

    def test_supported_fractional_timestamps_preserve_exact_observations(self):
        for fraction in ("1", "12", "123", "1234", "12345", "123456"):
            with self.subTest(fraction=fraction):
                before, after = pair()
                before["captured_at"] = "2026-11-17T00:00:00Z"
                after["captured_at"] = f"2026-11-17T00:00:00.{fraction}Z"
                result = classify(before, after)
                self.assertEqual(result["previous"], before)
                self.assertEqual(result["current"], after)
                self.assertEqual(result["decision"], "unchanged")

    def test_supported_fractional_chronology_compares_instants(self):
        before, after = pair()
        before["captured_at"] = "2026-11-17T00:00:00.123456Z"
        after["captured_at"] = "2026-11-17T00:00:00.123455Z"
        with self.assertRaises(ChangeError):
            classify(before, after)
        before["captured_at"] = "2026-11-17T00:00:00.1Z"
        after["captured_at"] = "2026-11-17T00:00:00.100000Z"
        self.assertEqual(classify(before, after)["decision"], "unchanged")

    def test_submicrosecond_timestamps_rejected_in_either_observation(self):
        for side in ("previous", "current", "both"):
            for fraction in ("1234569", "1234560", "0000001", "12345678901234567890"):
                with self.subTest(side=side, fraction=fraction):
                    before, after = pair()
                    if side in ("previous", "both"):
                        before["captured_at"] = f"2026-11-17T00:00:00.{fraction}Z"
                    if side in ("current", "both"):
                        current_fraction = "1234561" if side == "both" else fraction
                        after["captured_at"] = f"2026-11-17T00:00:00.{current_fraction}Z"
                    with self.assertRaises(ChangeError):
                        classify(before, after)

    def test_runtime_timestamp_guard_rejects_precision_without_schema(self):
        self.assertEqual(_timestamp("2026-11-17T00:00:00.123456Z").microsecond, 123456)
        for invalid in ("2026-11-17T00:00:00.1234569Z", "2026-11-17T00:00:00.1234561Z",
                        "2026-11-17T00:00:00.1234560Z", "2026-11-17T00:00:00Z\n"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ChangeError):
                    _timestamp(invalid)

    def test_trailing_line_terminators_fail_without_changing_inputs(self):
        setters = {
            "source_id": lambda obs, suffix: obs.update(source_id=obs["source_id"] + suffix),
            "material_id": lambda obs, suffix: obs.update(material_id=obs["material_id"] + suffix),
            "observation_id": lambda obs, suffix: obs.update(observation_id=obs["observation_id"] + suffix),
            "captured_at": lambda obs, suffix: obs.update(captured_at=obs["captured_at"] + suffix),
            "content_sha256": lambda obs, suffix: obs.update(content_sha256=obs["content_sha256"] + suffix),
            "parser_revision": lambda obs, suffix: obs.update(parser_revision=obs["parser_revision"] + suffix),
            "path": lambda obs, suffix: obs["claims"][0].update(path="price.input" + suffix),
            "evidence_ref": lambda obs, suffix: obs["claims"][0].update(evidence_ref=obs["claims"][0]["evidence_ref"] + suffix),
            "value": lambda obs, suffix: obs["claims"][0].update(value="1.25" + suffix),
            "unit": lambda obs, suffix: obs["claims"][0].update(unit="per_token" + suffix),
            "currency": lambda obs, suffix: obs["claims"][0].update(currency="USD" + suffix),
        }
        for field, setter in setters.items():
            for suffix in ("\r", "\n", "\r\n"):
                with self.subTest(field=field, suffix=repr(suffix)):
                    before, after = pair()
                    for obs in (before, after):
                        obs["claims"][0].update(kind="price", value="1.25", unit="per_token", currency="USD")
                        setter(obs, suffix)
                    originals = deepcopy((before, after))
                    with self.assertRaises(ChangeError):
                        classify(before, after)
                    self.assertEqual((before, after), originals)

    def test_malformed_direct_inputs_fail_closed(self):
        for invalid in (None, [], "observation", 1):
            with self.subTest(invalid=invalid):
                before, after = pair()
                for previous, current in ((invalid, after), (before, invalid)):
                    with self.assertRaises(ChangeError):
                        classify(previous, current)
        for key, invalid in (("captured_at", None), ("claims", ()), ("claims", [None])):
            with self.subTest(key=key, invalid=invalid):
                before, after = pair()
                after[key] = invalid
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


class ChangeDiagnosticTests(unittest.TestCase):
    def assert_safe_error(self, before, after, marker, expected):
        try:
            classify(before, after)
        except ChangeError as error:
            self.assertEqual(str(error), expected)
            self.assertLessEqual(len(str(error)), 80)
            self.assertIsNone(error.__cause__)
            self.assertNotIn(marker, "".join(traceback.format_exception(error)))
        else:
            self.fail("Invalid observation or result was accepted")

    def test_schema_errors_never_reflect_values_or_property_names(self):
        marker = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_ECHO!"
        before, after = pair()
        invalid_observations = []
        for change in (
            {"parser_revision": marker},
            {marker: "unexpected property"},
            {"claims": [{"nested": marker}]},
        ):
            invalid_observations.append({**after, **change})
        nested_extra = deepcopy(after)
        nested_extra["claims"][0][marker] = "unexpected nested property"
        invalid_observations.append(nested_extra)
        for index, invalid in enumerate(invalid_observations):
            with self.subTest(case=index):
                self.assert_safe_error(before, invalid, marker,
                                       "invalid draft observation: schema validation failed")

    def test_internal_result_error_never_reflects_nested_output(self):
        marker = "SYNTHETIC_PRIVATE_MARKER_DO_NOT_ECHO!"
        before, after = pair()
        after["claims"][0]["value"] = "synthetic-alias-change"
        # Fault injection exercises the internal result validator separately
        # from input rejection without changing either schema or valid inputs.
        with patch("src.changes._review_requirements", return_value=("review", marker, [marker])):
            self.assert_safe_error(before, after, marker,
                                   "internal change-set schema violation: validation failed")

    def test_calendar_error_does_not_chain_parser_exception(self):
        try:
            _timestamp("2026-02-30T12:00:00Z")
        except ChangeError as error:
            self.assertIsNone(error.__cause__)
            rendered = "".join(traceback.format_exception(error))
            self.assertNotIn("ValueError:", rendered)
            self.assertNotIn("During handling", rendered)
        else:
            self.fail("Invalid calendar instant was accepted")


if __name__ == "__main__":
    unittest.main()
