"""Adversarial offline, synthetic freshness boundaries for CP-11.01 (#53)."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from freshness import FreshnessError, evaluate
from jsonschema import Draft202012Validator

NOW = datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc)
BASE = "urn:pya:synthetic:"


def policy(claim_type="current_price", **kwargs):
    pinned = claim_type in {"version_pinned_fact", "immutable_release", "historical_evidence"}
    result = dict(schema_version="freshness-draft-0.1.0", synthetic=True,
                  decision_status="proposed", policy_id=BASE + "policy:local",
                  source_id=BASE + "source:fictional", claim_type=claim_type,
                  mode="pinned" if pinned else "current", event_triggers=["source_corrected"] if pinned else ["price_changed"],
                  rationale="Fictional rule for unit tests only")
    if not pinned:
        result["review_interval_seconds"] = 3600
    result.update(kwargs)
    return result


def observation(claim_type="current_price", **kwargs):
    result = dict(schema_version="freshness-draft-0.1.0", synthetic=True,
                  claim_id=BASE + "claim:fictional", source_id=BASE + "source:fictional",
                  claim_type=claim_type, observation_ref=BASE + "observation:fictional",
                  source_status="available", captured_at="2026-11-17T12:00:00Z",
                  checked_at="2026-11-17T14:30:00Z", effective_at="2026-11-17T11:00:00Z",
                  published_at="2026-11-17T13:00:00Z", snapshot_ref=BASE + "snapshot:v1")
    result.update(kwargs)
    return result


class FreshnessTests(unittest.TestCase):
    def check(self, p=None, o=None, events=()):
        return evaluate(p or policy(), o or observation(), as_of=NOW, events=events)

    def assert_invalid(self, p=None, o=None, events=()):
        with self.assertRaises(FreshnessError):
            self.check(p, o, events)

    def test_schema_is_valid_draft_202012(self):
        schema = json.loads((ROOT / "schemas/freshness-policy.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertFalse(list(validator.iter_errors(policy())))
        self.assertFalse(list(validator.iter_errors(policy("historical_evidence"))))
        for invalid in [policy(mode="pinned"), policy("immutable_release", review_interval_seconds=1),
                        policy(synthetic=False), policy(decision_status="accepted"),
                        policy(event_triggers=[], review_interval_seconds=None),
                        policy(source_id="https://non.synthetic/"), policy(review_interval_seconds=True),
                        policy(review_interval_seconds=-1), policy(unreviewed_extra=1)]:
            self.assertTrue(list(validator.iter_errors(invalid)), invalid)

    def test_time_is_qualified_and_fields_retained_separately(self):
        result = self.check()
        self.assertEqual(result["status"], "checked_as_of")
        self.assertFalse(result["publication_eligible"])
        self.assertEqual(result["checked_at"], "2026-11-17T14:30:00Z")
        self.assertEqual(result["captured_at"], "2026-11-17T12:00:00Z")
        self.assertEqual(result["effective_at"], "2026-11-17T11:00:00Z")
        self.assertEqual(result["published_at"], "2026-11-17T13:00:00Z")
        self.assertEqual(result["evaluated_at"], "2026-11-17T15:00:00Z")

    def test_source_scoped_threshold_boundary(self):
        self.assertEqual(self.check()["status"], "checked_as_of")
        self.assertEqual(self.check(o=observation(checked_at="2026-11-17T14:00:00Z"))["status"], "review_due")
        self.assertEqual(self.check(p=policy(review_interval_seconds=7200))["status"], "checked_as_of")

    def test_pinned_evidence_and_releases_do_not_expire_on_snapshot_change(self):
        for claim_type in ["version_pinned_fact", "historical_evidence", "immutable_release"]:
            p = policy(claim_type)
            old = observation(claim_type, captured_at="2001-01-01T00:00:00Z",
                              checked_at="2001-01-01T00:00:00Z", published_at="2001-01-02T00:00:00Z")
            result = self.check(p, old, events=("snapshot_created",))
            self.assertEqual(result["status"], "pinned")
            self.assertEqual(result["snapshot_ref"], BASE + "snapshot:v1")
            self.assertEqual(result["next_action"], "retain_version_reference_no_age_expiry")
            self.assertFalse(result["publication_eligible"])

    def test_unknown_checks_and_unavailable_sources_preserve_history(self):
        unchecked = observation()
        unchecked.pop("checked_at")
        self.assertEqual(self.check(o=unchecked)["status"], "unchecked")
        for state, expected in (("unknown", "source_unknown"), ("unavailable", "source_unavailable")):
            result = self.check(o=observation(source_status=state))
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["observation_ref"], BASE + "observation:fictional")

    def test_rights_and_source_policy_change_hold_every_claim_class(self):
        for claim_type in ("historical_evidence", "current_price"):
            for event in ("rights_changed", "source_policy_changed"):
                result = self.check(policy(claim_type), observation(claim_type), events=(event,))
                self.assertEqual(result["status"], "rights_hold")
                self.assertFalse(result["publication_eligible"])

    def test_triggers_and_no_universal_interval(self):
        p = policy()
        p.pop("review_interval_seconds")
        self.assertEqual(self.check(p)["status"], "as_of_only")
        self.assertEqual(self.check(p, events=("price_changed",))["status"], "event_review")
        self.assertEqual(self.check(p, events=("snapshot_created",))["status"], "as_of_only")
        self.assertEqual(self.check(policy("historical_evidence"), observation("historical_evidence"),
                                    events=("source_corrected",))["status"], "event_review")

    def test_future_effective_must_not_be_described_as_current(self):
        result = self.check(o=observation(effective_at="2026-11-18T00:00:00Z"))
        self.assertEqual(result["status"], "not_yet_effective")

    def test_malformed_claim_and_policy_fail_closed(self):
        self.assert_invalid(p=policy(source_id=BASE + "source:other"))
        self.assert_invalid(o=observation(claim_type="current_availability"))
        self.assert_invalid(o=observation(synthetic=False))
        self.assert_invalid(o=observation(claim_id="urn:pya:real:claim:other"))
        self.assert_invalid(o=observation(captured_at="2026-11-17T12:00:00+00:00"))
        self.assert_invalid(o=observation(captured_at="2026-02-30T12:00:00Z"))
        self.assert_invalid(o=observation(checked_at="2026-11-17T11:00:00Z"))
        self.assert_invalid(o=observation(checked_at="2026-11-18T12:00:00Z"))
        self.assert_invalid(o=observation(source_status="live"))
        self.assert_invalid(o=observation(source_status={"unsound": "value"}))
        self.assert_invalid(o=observation(extra_field="unsafe"))
        self.assert_invalid(events=("unrecognized_event",))
        self.assert_invalid(p=policy(mode="pinned"))
        with self.assertRaises(FreshnessError):
            evaluate(policy(), observation(), as_of=datetime(2026, 11, 17))

    def test_deterministic_pure_result_and_unknown_handling(self):
        before = deepcopy(observation())
        pol = policy()
        first = self.check(pol, before)
        self.assertEqual(first, self.check(pol, before))
        self.assertEqual(before, observation())
        self.assertEqual(first["policy_id"], pol["policy_id"])
        self.assertEqual(first["next_action"], "retain_as_of_disclosure_and_monitor")


if __name__ == "__main__":
    unittest.main()
