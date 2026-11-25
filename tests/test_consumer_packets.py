"""Independent offline consistency failures; no consumer runtime evidence."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.consumer_handoffs import packets as P

ROOT = Path(__file__).resolve().parents[1]


def encode(value):
    return json.dumps(value).encode()


class ConsumerPacketTests(unittest.TestCase):
    def setUp(self):
        self.packet_bytes = (ROOT / 'examples/synthetic/consumer-packet.json').read_bytes()
        self.packet = json.loads(self.packet_bytes)
        self.manifest_bytes = (ROOT / 'examples/synthetic-release.json').read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        self.artifacts = {e['path']: (ROOT / e['path']).read_bytes()
                          for e in self.manifest['artifacts']}

    def check(self, packet=None, manifest=None, artifacts=None, consumer='website'):
        return P.check_packet(encode(packet) if packet is not None else self.packet_bytes,
                              encode(manifest) if manifest is not None else self.manifest_bytes,
                              artifacts if artifacts is not None else self.artifacts,
                              consumer=consumer)

    def reanchor(self, manifest):
        packet = deepcopy(self.packet)
        packet['manifest'].update(id=manifest['id'], revision=manifest['revision'],
                                  sha256=hashlib.sha256(encode(manifest)).hexdigest())
        packet['artifacts'] = deepcopy(manifest['artifacts'])
        return packet

    def test_current_manifest_bytes_pass_without_io(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('I/O')), \
                patch('socket.socket', side_effect=AssertionError('network')):
            self.assertEqual(self.check(), 'unresolved')
            self.assertEqual(self.check(), 'unresolved')
        for consumer in P.CONSUMERS:
            for state in ('rehearsal', 'unresolved', 'rejected'):
                packet = deepcopy(self.packet)
                packet.update(consumer=consumer, status=state)
                self.assertEqual(self.check(packet, consumer=consumer), state)

    def test_example_validator_checks_packet_semantics(self):
        spec = importlib.util.spec_from_file_location('packet_examples', ROOT / 'scripts/validate_examples.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('examples', 'schemas'):
                shutil.copytree(ROOT / directory, root / directory)
            self.assertEqual(module.validate(root), [])
            self.packet['manifest']['sha256'] = '0' * 64
            self.assertTrue(P._VALIDATORS['consumer-receipt'].is_valid(self.packet))
            (root / 'examples/synthetic/consumer-packet.json').write_bytes(encode(self.packet))
            self.assertIn('synthetic/consumer-packet.json: offline packet consistency failed',
                          module.validate(root))

    def test_wrong_consumer_version_and_adoption_claims_reject(self):
        with self.assertRaises(P.PacketError):
            self.check(consumer='apple')
        for field, value in [('consumer', 'unknown'), ('schema_version', '1.0.0'),
                             ('synthetic', False), ('status', 'adopted'),
                             ('status', 'production-ready'), ('generated_code_passed', True),
                             ('schema_pass_establishes_adoption', True)]:
            packet = deepcopy(self.packet)
            packet[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(P.PacketError):
                self.check(packet)
        for name in P.CONSUMERS:
            packet = deepcopy(self.packet)
            packet['scopes'][name]['receiving_acceptance'] = 'accepted'
            with self.assertRaises(P.PacketError):
                self.check(packet)

    def test_manifest_byte_identity_revision_and_hash_are_independent(self):
        for field, value in [('id', 'urn:pya:synthetic:release:other'), ('revision', 2),
                             ('sha256', '0' * 64), ('schema_version', 'other')]:
            packet = deepcopy(self.packet)
            packet['manifest'][field] = value
            with self.subTest(field=field), self.assertRaises(P.PacketError):
                self.check(packet)
        with self.assertRaises(P.PacketError):
            P.check_packet(self.packet_bytes, self.manifest_bytes + b' ', self.artifacts,
                           consumer='website')

    def test_artifact_bytes_and_exact_entry_set_reject(self):
        for variant in ('tampered', 'missing', 'extra'):
            artifacts = dict(self.artifacts)
            first = next(iter(artifacts))
            if variant == 'tampered':
                artifacts[first] += b' '
            elif variant == 'missing':
                del artifacts[first]
            else:
                artifacts['examples/extra.json'] = artifacts[first]
            with self.subTest(variant=variant), self.assertRaises(P.PacketError):
                self.check(artifacts=artifacts)
        for field, value in [('path', 'examples/other.json'), ('record_id', 'urn:pya:synthetic:other'),
                             ('revision', 2), ('sha256', '0' * 64)]:
            packet = deepcopy(self.packet)
            packet['artifacts'][0][field] = value
            with self.subTest(field=field), self.assertRaises(P.PacketError):
                self.check(packet)

    def test_reanchored_manifest_cannot_hide_artifact_identity_or_version_mismatch(self):
        for field, value in [('id', 'urn:pya:synthetic:other'), ('revision', 2),
                             ('schema_version', 'other'), ('synthetic', False)]:
            manifest = deepcopy(self.manifest)
            entry = manifest['artifacts'][0]
            artifacts = dict(self.artifacts)
            record = json.loads(artifacts[entry['path']])
            record[field] = value
            artifacts[entry['path']] = encode(record)
            entry['sha256'] = hashlib.sha256(artifacts[entry['path']]).hexdigest()
            with self.subTest(field=field), self.assertRaises(P.PacketError):
                self.check(self.reanchor(manifest), manifest, artifacts)

    def test_duplicate_manifest_and_packet_entries_and_unsafe_paths_reject(self):
        manifest = deepcopy(self.manifest)
        manifest['artifacts'].append(deepcopy(manifest['artifacts'][0]))
        with self.assertRaises(P.PacketError):
            self.check(self.reanchor(manifest), manifest)
        packet = deepcopy(self.packet)
        packet['artifacts'].append(deepcopy(packet['artifacts'][0]))
        with self.assertRaises(P.PacketError):
            self.check(packet)
        for path in ('../outside.json', '/etc/passwd', 'examples/../other.json',
                     'https://example.invalid/data', 'examples\\other.json', 'examples/%2e.json'):
            artifacts = {path: b'{}'}
            with self.subTest(path=path), self.assertRaises(P.PacketError):
                self.check(artifacts=artifacts)

    def test_malformed_manifest_and_rehashed_artifact_reject(self):
        for raw in (b'{"id":1,"id":2}', b'\xff', b'{"value":NaN}'):
            with self.assertRaises(P.PacketError):
                P.check_packet(self.packet_bytes, raw, self.artifacts, consumer='website')
            manifest = deepcopy(self.manifest)
            entry = manifest['artifacts'][0]
            artifacts = dict(self.artifacts)
            artifacts[entry['path']] = raw
            entry['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(P.PacketError):
                self.check(self.reanchor(manifest), manifest, artifacts)

    def test_malformed_and_over_limit_input_has_fixed_diagnostics(self):
        cases = [b'', b'\xff', b'{"payload":NaN}', b'{"payload":1.0}',
                 b'{"payload":1,"payload":2}', b'{"payload":"\\ud800"}',
                 b'[' * 33 + b']' * 33, encode({'payload': 'x' * 8193}),
                 b'[' + b'0,' * 10001 + b'0]', b'x' * (P.MAX_DOCUMENT_BYTES + 1)]
        for raw in cases:
            with self.subTest(size=len(raw)), self.assertRaises(P.PacketError) as caught:
                P.check_packet(raw, self.manifest_bytes, self.artifacts, consumer='website')
            self.assertEqual(str(caught.exception), 'Synthetic packet consistency check failed.')
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)
        for artifacts in ({}, {'examples/a.json': b'x' * (P.MAX_ARTIFACT_BYTES + 1)},
                          {f'examples/a-{i}.json': b'{}' for i in range(33)},
                          {f'examples/a-{i}.json': b'x' * P.MAX_ARTIFACT_BYTES for i in range(9)}):
            with self.assertRaises(P.PacketError):
                self.check(artifacts=artifacts)


if __name__ == '__main__':
    unittest.main()
