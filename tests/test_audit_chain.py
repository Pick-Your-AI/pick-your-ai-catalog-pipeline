"""Synthetic offline audit snapshots; no real decisions or receipts."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from src.audit import chain


CHAIN = "urn:pya:synthetic:audit:one"
OTHER_CHAIN = "urn:pya:synthetic:audit:other"
OBJECT = "urn:pya:synthetic:claim:one"
EVENT = b'{"id":"urn:pya:synthetic:event:one","state":"attempted"}'
OBJECT_BYTES = b'{"value":"unknown","reason":"synthetic fixture"}'


class AuditChainTest(unittest.TestCase):
    def add(self, entries=(), event=EVENT, objects=None):
        return chain.append(
            entries, chain_id=CHAIN, event=event,
            affected_objects={OBJECT: OBJECT_BYTES} if objects is None else objects,
            expected_head=entries[-1].digest if entries else chain.empty_head(CHAIN),
            expected_count=len(entries))

    def check(self, entries, trusted):
        return chain.verify(entries, chain_id=CHAIN,
                            expected_head=trusted[-1].digest,
                            expected_count=len(trusted))

    def test_empty_snapshot_has_chain_bound_checkpoint(self):
        head = chain.empty_head(CHAIN)
        self.assertNotEqual(head, chain.empty_head(OTHER_CHAIN))
        self.assertEqual(chain.verify((), chain_id=CHAIN, expected_head=head,
                                      expected_count=0), head)
        with self.assertRaises(chain.ChainError):
            chain.verify((), chain_id=CHAIN, expected_head="0" * 64, expected_count=0)
        with self.assertRaises(TypeError):
            chain.verify((), chain_id=CHAIN)

    def test_append_retains_prior_snapshot_and_exact_bytes(self):
        first = self.add()
        second = self.add(first, b'{"id":"urn:pya:synthetic:event:two"}')
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 2)
        self.assertIs(first[0], second[0])
        self.assertEqual(second[1].previous_digest, first[0].digest)
        self.assertEqual(self.check(second, second), second[-1].digest)
        differently_formatted = self.add(event=b' {"state":"attempted", "id":"urn:pya:synthetic:event:one"} ')
        self.assertNotEqual(first[-1].digest, differently_formatted[-1].digest)
        self.assertEqual(differently_formatted[-1].event[:1], b" ")

    def test_objects_sorted_and_copied_without_dictionary_alias(self):
        extra = "urn:pya:synthetic:claim:two"
        objects = {extra: b'{"value":2}', OBJECT: OBJECT_BYTES}
        snapshot = self.add(objects=objects)
        reversed_order = self.add(objects=dict(reversed(list(objects.items()))))
        self.assertEqual(snapshot, reversed_order)
        objects[OBJECT] = b'{"value":3}'
        objects.clear()
        self.assertEqual(snapshot[0].affected_objects[0], (OBJECT, OBJECT_BYTES))
        with self.assertRaises(FrozenInstanceError):
            snapshot[0].event = b'{}'
        self.check(snapshot, snapshot)

    def test_modified_root_tail_prior_digest_and_affected_bytes_rejected(self):
        snapshot = self.add(self.add())
        changes = [
            (0, {"event": b'{"state":"accepted"}'}),
            (1, {"event": b'{"state":"accepted"}'}),
            (1, {"previous_digest": "0" * 64}),
            (0, {"affected_objects": ((OBJECT, b'{"value":true}'),)}),
            (0, {"affected_objects": (("urn:pya:synthetic:claim:other", OBJECT_BYTES),)}),
            (1, {"digest": "0" * 64}),
            (0, {"chain_id": OTHER_CHAIN}),
        ]
        for index, changeset in changes:
            with self.subTest(changes=changeset), self.assertRaises(chain.ChainError):
                altered = list(snapshot)
                altered[index] = replace(altered[index], **changeset)
                self.check(tuple(altered), snapshot)

    def test_removal_insertion_reordering_and_replay_fail_checkpoint(self):
        snapshot = self.add(self.add(self.add()))
        variants = [snapshot[:-1], snapshot[1:], snapshot[:1] + snapshot[2:],
                    tuple(reversed(snapshot)), snapshot[:1] + snapshot,
                    snapshot + snapshot[-1:], (snapshot[0], snapshot[0], snapshot[2]), ()]
        for altered in variants:
            with self.subTest(count=len(altered)), self.assertRaises(chain.ChainError):
                self.check(altered, snapshot)
        with self.assertRaises(chain.ChainError):
            chain.append(snapshot[:-1], chain_id=CHAIN, event=EVENT,
                         affected_objects={OBJECT: OBJECT_BYTES},
                         expected_head=snapshot[-1].digest, expected_count=3)

    def test_recomputed_chain_requires_external_original_checkpoint(self):
        original = self.add()
        replacement = self.add(event=b'{"state":"withdrawn","synthetic":true}')
        # A self-consistent rewritten chain passes its own checksum. It cannot
        # pass the original independently retained checkpoint.
        self.check(replacement, replacement)
        with self.assertRaises(chain.ChainError):
            self.check(replacement, original)
        for head, count in [(original[-1].digest, 0), ("f" * 64, 1)]:
            with self.assertRaises(chain.ChainError):
                chain.verify(original, chain_id=CHAIN, expected_head=head, expected_count=count)
        with self.assertRaises(chain.ChainError):
            chain.verify(original, chain_id=OTHER_CHAIN,
                         expected_head=original[-1].digest, expected_count=1)

    def test_ambiguous_invalid_numeric_and_unicode_json_rejected(self):
        bad = [b'{"a":1,"a":2}', b'{"nested":{"a":1,"a":2}}',
               b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1.5}', b'{"a":1e2}',
               b'{}{}', b'[]', b'null', b'{"a":"\xff"}', b'{"a":"\\ud800"}',
               b'{"\\ud800":0}', b'\xef\xbb\xbf{}', b'', b'{' + b' ' * 10]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(chain.ChainError):
                self.add(event=value)
            with self.subTest(affected=value), self.assertRaises(chain.ChainError):
                self.add(objects={OBJECT: value})

    def test_depth_nodes_precision_and_byte_bounds(self):
        accepted = ('{"n":' + '9' * chain.MAX_INTEGER_DIGITS + '}').encode()
        self.check(self.add(event=accepted), self.add(event=accepted))
        invalid = [('{"n":' + '9' * (chain.MAX_INTEGER_DIGITS + 1) + '}').encode(),
                   b'{"x":' + b'[' * (chain.MAX_DEPTH + 1) + b'0' + b']' * (chain.MAX_DEPTH + 1) + b'}',
                   b'{"x":[' + b'0,' * chain.MAX_NODES + b'0]}',
                   json.dumps({"x": "a" * chain.MAX_VALUE_BYTES}).encode()]
        for value in invalid:
            with self.subTest(size=len(value)), self.assertRaises(chain.ChainError):
                self.add(event=value)
        exact_bytes = b'{"x":"' + b'a' * (chain.MAX_VALUE_BYTES - 8) + b'"}'
        self.assertEqual(len(exact_bytes), chain.MAX_VALUE_BYTES)
        self.add(event=exact_bytes)
        with self.assertRaises(chain.ChainError):
            self.add(event=exact_bytes + b' ')

    def test_mutable_recursive_and_malformed_snapshots_rejected(self):
        recursive = {}
        recursive["cycle"] = recursive
        for event in [recursive, bytearray(EVENT), memoryview(EVENT), True]:
            with self.subTest(type=type(event)), self.assertRaises(chain.ChainError):
                self.add(event=event)
        snapshot = self.add()
        malformed = [replace(snapshot[0], sequence=True),
                     replace(snapshot[0], affected_objects=[]),
                     replace(snapshot[0], affected_objects=((OBJECT, OBJECT_BYTES),) * 2),
                     replace(snapshot[0], affected_objects=((OBJECT,),)),
                     replace(snapshot[0], digest="A" * 64)]
        for entry in malformed:
            with self.assertRaises(chain.ChainError):
                self.check((entry,), snapshot)
        with self.assertRaises(chain.ChainError):
            self.check(list(snapshot), snapshot)
        for count in [True, -1, chain.MAX_EVENTS + 1, "1"]:
            with self.assertRaises(chain.ChainError):
                chain.verify(snapshot, chain_id=CHAIN,
                             expected_head=snapshot[-1].digest, expected_count=count)

    def test_object_count_identifiers_and_aggregate_limits(self):
        for objects in [{}, {"": b'{}'}, {"x\n": b'{}'}, {"x" * 257: b'{}'},
                        {str(i): b'{}' for i in range(chain.MAX_OBJECTS + 1)}]:
            with self.assertRaises(chain.ChainError):
                self.add(objects=objects)
        accepted_objects = {f"urn:pya:synthetic:claim:{i}": b'{}' for i in range(chain.MAX_OBJECTS)}
        self.add(objects=accepted_objects)
        # Small configured ceilings exercise exact aggregate and count edges
        # without allocating a large fixture or weakening production defaults.
        size = len(EVENT) + len(OBJECT.encode()) + len(OBJECT_BYTES)
        with patch.object(chain, "MAX_CHAIN_BYTES", size):
            first = self.add()
            with self.assertRaises(chain.ChainError):
                self.add(first)
        with patch.object(chain, "MAX_EVENTS", 1):
            first = self.add()
            with self.assertRaises(chain.ChainError):
                self.add(first)


if __name__ == "__main__":
    unittest.main()
