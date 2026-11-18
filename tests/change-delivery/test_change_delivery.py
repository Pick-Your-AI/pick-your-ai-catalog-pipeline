"""Synthetic-only adversarial change-delivery tests (no IO or network)."""
import copy
import unittest

from src.delivery import DeliveryError, recover_from_snapshot, replay


def event(sequence, kind="release_available", artifact="synthetic:catalog", revision="r1"):
    pairs = {
        "release_available": ("optional_review", "A new catalog revision is available."),
        "correction": ("review_correction", "Catalog information was corrected."),
        "mandatory_withdrawal": ("withhold_and_purge", "This catalog version must be withdrawn."),
    }
    action, public = pairs[kind]
    return {"event_id": f"synthetic:ev-{sequence}", "sequence": sequence, "kind": kind,
            "required_action": action, "public_explanation": public,
            "affected_versions": [{"artifact_id": artifact, "revision": revision}]}


def feed(events):
    return {"schema_version": "0.1-draft", "stream_id": "synthetic:catalog-feed",
            "synthetic": True, "publication_eligible": False, "events": events}


class ChangeDeliveryTests(unittest.TestCase):
    def test_ordered_batch_withdrawal(self):
        x = replay(feed([event(1), event(2, "mandatory_withdrawal")]))
        self.assertEqual(x["state"]["cursor"], 2)
        self.assertEqual(x["state"]["withheld_versions"], ["synthetic:catalog@r1"])
        self.assertEqual(x["proposed_receipts"][1]["required_action"], "withhold_and_purge")
        self.assertFalse(x["publication_eligible"] or x["delivery_authorized"])

    def test_out_of_order_can_be_sorted_without_gap(self):
        x = replay(feed([event(3), event(1), event(2)]))
        self.assertEqual(x["state"]["cursor"], 3)
        self.assertFalse(x["requires_resync"])

    def test_gap_blocks_all_access(self):
        x = replay(feed([event(1), event(3, "mandatory_withdrawal")]))
        self.assertEqual(x["state"]["cursor"], 1)
        self.assertTrue(x["requires_resync"] and x["block_all_access"])

    def test_exact_duplicate_batch_is_idempotent(self):
        batch = feed([event(1, "mandatory_withdrawal")])
        first = replay(batch)
        second = replay(batch, first["state"])
        self.assertEqual(second["proposed_receipts"], [])
        self.assertEqual(second["state"], first["state"])

    def test_duplicate_sequence_conflict_refused(self):
        with self.assertRaises(DeliveryError):
            replay(feed([event(1), event(1, "mandatory_withdrawal")]))

    def test_modified_old_event_forces_resync(self):
        first = replay(feed([event(1)]))
        changed = event(1, "correction")
        x = replay(feed([changed]), first["state"])
        self.assertTrue(x["block_all_access"])

    def test_future_release_never_clears_withdrawal(self):
        first = replay(feed([event(1, "mandatory_withdrawal")]))
        second = replay(feed([event(2, "release_available")]), first["state"])
        self.assertEqual(second["state"]["withheld_versions"], ["synthetic:catalog@r1"])

    def test_public_explanation_cannot_be_untrusted(self):
        x = event(1)
        x["public_explanation"] = "private source notes"
        with self.assertRaisesRegex(DeliveryError, "invalid synthetic change feed"):
            replay(feed([x]))

    def test_withdrawal_cannot_request_optional_action(self):
        x = event(1, "mandatory_withdrawal")
        x["required_action"] = "optional_review"
        with self.assertRaises(DeliveryError):
            replay(feed([x]))

    def test_unsynthetic_and_extra_keys_denied(self):
        for delta in ({"synthetic": False}, {"publication_eligible": True}, {"secret": "x"}):
            x = feed([event(1)])
            x.update(delta)
            with self.assertRaises(DeliveryError):
                replay(x)

    def test_trailing_newline_in_identifier_denied(self):
        x = event(1)
        x["event_id"] += "\n"
        with self.assertRaises(DeliveryError):
            replay(feed([x]))

    def test_false_boolean_sequence_denied(self):
        x = event(1)
        x["sequence"] = True
        with self.assertRaises(DeliveryError):
            replay(feed([x]))

    def test_stream_mismatch_denied(self):
        first = replay(feed([event(1)]))
        other = feed([event(2)])
        other["stream_id"] = "synthetic:another"
        with self.assertRaises(DeliveryError):
            replay(other, first["state"])

    def test_recovery_requires_complete_snapshot_and_retains_block(self):
        old = replay(feed([event(1)]))["state"]
        snap = {"schema_version": "0.1-draft", "stream_id": old["stream_id"],
                "synthetic": True, "publication_eligible": False, "cursor": 100,
                "complete_withdrawals": [{"artifact_id": "synthetic:catalog", "revision": "r1"}]}
        x = recover_from_snapshot(snap, old)
        self.assertTrue(x["block_all_access"] and x["requires_external_acceptance"])
        self.assertEqual(x["state"]["withheld_versions"], ["synthetic:catalog@r1"])
        replay_old = replay(feed([event(1)]), x["state"])
        self.assertTrue(replay_old["requires_resync"])
        new = replay(feed([event(101)]), x["state"])
        self.assertTrue(new["block_all_access"])

    def test_stale_or_other_stream_snapshot_denied(self):
        old = replay(feed([event(1)]))["state"]
        snapshot = {"schema_version": "0.1-draft", "stream_id": old["stream_id"],
                    "synthetic": True, "publication_eligible": False, "cursor": 0,
                    "complete_withdrawals": []}
        with self.assertRaises(DeliveryError):
            recover_from_snapshot(snapshot, old)
        snapshot["cursor"] = 3
        snapshot["stream_id"] = "synthetic:other"
        with self.assertRaises(DeliveryError):
            recover_from_snapshot(snapshot, old)

    def test_replay_does_not_mutate_input_state(self):
        first = replay(feed([event(1)]))["state"]
        saved = copy.deepcopy(first)
        replay(feed([event(2)]), first)
        self.assertEqual(first, saved)

    def test_invalid_state_rejected_without_reflection(self):
        x = {"stream_id": "synthetic:catalog-feed", "cursor": -5,
             "hashes": {}, "withheld_versions": [], "recovery_pending": False}
        with self.assertRaisesRegex(DeliveryError, "invalid synthetic change feed"):
            replay(feed([event(1)]), x)


    def test_distinct_sequences_cannot_reuse_event_id(self):
        initial = event(1)
        another = event(2, "mandatory_withdrawal")
        another["event_id"] = initial["event_id"]
        with self.assertRaisesRegex(DeliveryError, "conflicting synthetic event identity"):
            replay(feed([initial, another]))

    def test_exact_same_event_twice_within_batch_is_idempotent(self):
        x = replay(feed([event(1), event(1)]))
        self.assertEqual(x["state"]["cursor"], 1)
        self.assertEqual(len(x["proposed_receipts"]), 1)

    def test_snapshot_omitting_prior_withdrawal_fails_closed(self):
        initial = replay(feed([event(1, "mandatory_withdrawal")]))["state"]
        snapshot = {"schema_version": "0.1-draft", "stream_id": initial["stream_id"],
                    "synthetic": True, "publication_eligible": False, "cursor": 2,
                    "complete_withdrawals": []}
        with self.assertRaisesRegex(DeliveryError, "synthetic snapshot omits prior withdrawal"):
            recover_from_snapshot(snapshot, initial)
        self.assertEqual(initial["withheld_versions"], ["synthetic:catalog@r1"])
        snapshot["complete_withdrawals"] = [
            {"artifact_id": "synthetic:catalog", "revision": "r1"}]
        recovered = recover_from_snapshot(snapshot, initial)
        self.assertTrue(recovered["block_all_access"] and recovered["requires_external_acceptance"])
        self.assertEqual(recovered["state"]["withheld_versions"], initial["withheld_versions"])

    def test_persisted_state_rejects_trailing_line_terminators(self):
        initial = replay(feed([event(1, "mandatory_withdrawal")]))["state"]
        invalid_hashes = copy.deepcopy(initial)
        invalid_hashes["hashes"] = {"1\n": "a" * 64}
        invalid_withdrawn = copy.deepcopy(initial)
        invalid_withdrawn["withheld_versions"] = ["synthetic:catalog@r1\n"]
        for bad in (invalid_hashes, invalid_withdrawn):
            with self.assertRaisesRegex(DeliveryError, "invalid synthetic change feed"):
                replay(feed([event(2)]), bad)


    def test_gap_block_survives_retransmitting_only_old_events(self):
        partial = replay(feed([event(1), event(3, "mandatory_withdrawal")]))
        self.assertEqual(partial["state"]["cursor"], 1)
        self.assertEqual(partial["state"]["highest_observed_sequence"], 3)
        again = replay(feed([event(1)]), partial["state"])
        self.assertTrue(again["block_all_access"] and again["requires_resync"])

    def test_gap_block_clears_only_after_full_contiguous_replay(self):
        partial = replay(feed([event(1), event(3)]))
        still_blocked = replay(feed([event(2)]), partial["state"])
        self.assertEqual(still_blocked["state"]["cursor"], 2)
        self.assertTrue(still_blocked["block_all_access"])
        complete = replay(feed([event(3)]), still_blocked["state"])
        self.assertEqual(complete["state"]["cursor"], 3)
        self.assertFalse(complete["block_all_access"])
        self.assertFalse(complete["requires_resync"])

    def test_integral_float_sequence_rejected_as_noncanonical(self):
        x = event(1)
        x["sequence"] = 1.0
        with self.assertRaisesRegex(DeliveryError, "noncanonical synthetic sequence"):
            replay(feed([x]))

    def test_noncanonical_state_and_snapshot_cursors_denied(self):
        initial = replay(feed([event(1)]))["state"]
        for key in ("cursor", "highest_observed_sequence"):
            invalid = copy.deepcopy(initial)
            invalid[key] = 1.0
            with self.assertRaisesRegex(DeliveryError, "noncanonical synthetic sequence"):
                replay(feed([event(2)]), invalid)
        snapshot = {"schema_version": "0.1-draft", "stream_id": initial["stream_id"],
                    "synthetic": True, "publication_eligible": False, "cursor": 2.0,
                    "complete_withdrawals": []}
        with self.assertRaisesRegex(DeliveryError, "noncanonical synthetic sequence"):
            recover_from_snapshot(snapshot, initial)

    def test_history_capacity_blocks_before_invalid_state(self):
        initial = {"stream_id": "synthetic:catalog-feed", "cursor": 10000,
                   "highest_observed_sequence": 10000,
                   "hashes": {str(i): "a" * 64 for i in range(1, 10001)},
                   "withheld_versions": [], "recovery_pending": False}
        x = replay(feed([event(10001)]), initial)
        self.assertTrue(x["block_all_access"] and x["requires_resync"])
        self.assertEqual(x["state"]["cursor"], 10000)
        self.assertEqual(len(x["state"]["hashes"]), 10000)

    def test_withdrawal_capacity_blocks_before_invalid_state(self):
        initial = {"stream_id": "synthetic:catalog-feed", "cursor": 0,
                   "highest_observed_sequence": 0, "hashes": {},
                   "withheld_versions": [f"synthetic:item-{i}@r1" for i in range(10000)],
                   "recovery_pending": False}
        x = replay(feed([event(1, "mandatory_withdrawal")]), initial)
        self.assertTrue(x["block_all_access"] and x["requires_resync"])
        self.assertEqual(x["state"]["cursor"], 0)
        self.assertEqual(len(x["state"]["withheld_versions"]), 10000)

    def test_snapshot_cannot_skip_unresolved_observed_sequence(self):
        partial = replay(feed([event(1), event(3)]))["state"]
        snapshot = {"schema_version": "0.1-draft", "stream_id": partial["stream_id"],
                    "synthetic": True, "publication_eligible": False, "cursor": 2,
                    "complete_withdrawals": []}
        with self.assertRaisesRegex(DeliveryError, "invalid synthetic snapshot position"):
            recover_from_snapshot(snapshot, partial)

if __name__ == "__main__":
    unittest.main()
