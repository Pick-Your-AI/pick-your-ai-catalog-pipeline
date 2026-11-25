"""Black-box synthetic identity and exact-revision contract regressions (Refs #58)."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from src.consumer_handoffs.packets import PacketError, check_packet

ROOT = Path(__file__).resolve().parents[1]
REVISIONS = (2**31, 2**53 + 1, 10**48 + 12345)


def encode(value):
    return json.dumps(value, ensure_ascii=True).encode('utf-8')


class ConsumerPacketEdgesTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((ROOT / 'examples/synthetic/consumer-packet.json').read_bytes())
        self.manifest = json.loads((ROOT / 'examples/synthetic-release.json').read_bytes())
        self.records = {r['path']: json.loads((ROOT / r['path']).read_bytes())
                        for r in self.manifest['artifacts']}
        self.path = self.manifest['artifacts'][0]['path']

    def anchor(self):
        for entry in self.manifest['artifacts']:
            record = self.records[entry['path']]
            entry.update(record_id=record['id'], revision=record['revision'],
                         sha256=hashlib.sha256(encode(record)).hexdigest())
        self.packet['artifacts'] = copy.deepcopy(self.manifest['artifacts'])

    def check(self):
        manifest_bytes = encode(self.manifest)
        self.packet['manifest'].update(id=self.manifest['id'],
                                      sha256=hashlib.sha256(manifest_bytes).hexdigest())
        return check_packet(encode(self.packet), manifest_bytes,
                            {p: encode(r) for p, r in self.records.items()}, consumer='website')

    def subject(self, location):
        return {'packet': self.packet, 'manifest': self.manifest,
                'artifact': self.records[self.path]}[location]

    def nested_identifiers(self):
        rights = self.manifest['rights_decision_ids']
        if len(rights) == 1:
            rights.append('urn:pya:synthetic:rights:offline-2')
        fields = [(f'rights_decision_ids[{index}]', rights, index)
                  for index in range(len(rights))]
        for path, record in self.records.items():
            record['relationships'] = [
                {'relation': 'cites', 'target_id': record['id'], 'target_revision': 1},
                {'relation': 'derived_from', 'target_id': record['id'], 'target_revision': 1},
            ]
            for index, relationship in enumerate(record['relationships']):
                fields.append((f'{path}.relationships[{index}]', relationship, 'target_id'))
            for index, claim in enumerate(record['claims']):
                label = f'{path}.claims[{index}]'
                fields.append((label + '.id', claim, 'id'))
                claim['evidence']['receipt_ref'] = 'urn:pya:synthetic:receipt:offline-1'
                fields.append((label + '.evidence', claim['evidence'], 'receipt_ref'))
                if len(claim['sources']) == 1:
                    claim['sources'].append(copy.deepcopy(claim['sources'][0]))
                for source_index, source in enumerate(claim['sources']):
                    for key in ('source_id', 'material_id'):
                        fields.append((f'{label}.sources[{source_index}].{key}', source, key))
        return fields

    def test_nested_id_control_suffixes_reject_after_reanchoring(self):
        for index in range(len(self.nested_identifiers())):
            for suffix in ('\n', '\r', '\t', '\x00', '\x1f', '\x7f', '\x85', '\u2028', '\u2029'):
                self.setUp()
                label, subject, key = self.nested_identifiers()[index]
                with self.subTest(field=label, suffix=repr(suffix)):
                    subject[key] += suffix
                    self.anchor()
                    with self.assertRaises(PacketError):
                        self.check()

    def test_nested_id_grammar_neighbors_remain_accepted(self):
        for index in range(len(self.nested_identifiers())):
            for value in ('urn:pya:a0', 'urn:pya:0a', 'urn:pya:a:._-09',
                          'urn:pya:synthetic:neighbor_2-0.1'):
                self.setUp()
                label, subject, key = self.nested_identifiers()[index]
                with self.subTest(field=label, value=value):
                    subject[key] = value
                    self.anchor()
                    self.assertEqual(self.check(), 'unresolved')

    def test_claim_path_requires_complete_existing_grammar(self):
        for value, valid in [('a0', True), ('a._-09', True), ('spec.context_tokens', True),
                             ('a', False), ('0a', False), ('spec.context_tokens\n', False),
                             ('spec.context_tokens\r', False), ('spec.context_tokens\u2028', False)]:
            with self.subTest(value=value):
                self.setUp()
                self.records[self.path]['claims'][-1]['path'] = value
                self.anchor()
                if valid:
                    self.assertEqual(self.check(), 'unresolved')
                else:
                    with self.assertRaises(PacketError):
                        self.check()

    def test_identifier_looking_free_form_text_remains_unchanged(self):
        value = 'urn:pya:free-form:untrusted\n\t\u2028'
        record = self.records[self.path]
        record['display_name'] = value
        record['unknowns'] = [value]
        claim = record['claims'][0]
        claim.update(value_type='string', value=value, unit=value, conditions=[value])
        claim['evidence']['basis'] = value
        claim['sources'][0]['source_revision'] = value
        unknown_claim = record['claims'][-1]
        unknown_claim.update(value_type='unknown', unknown_reason=value)
        unknown_claim.pop('value', None)
        self.manifest['limitations'] = [value]
        for scope in self.packet['scopes'].values():
            for key in ('mapping_limits', 'notices', 'precision_constraints',
                        'unsupported_fields', 'receiving_criteria'):
                scope[key] = [value]
            scope['acceptance_unknown_reason'] = value
        self.anchor()
        before = copy.deepcopy((self.manifest, self.records))
        self.assertEqual(self.check(), 'unresolved')
        self.assertEqual((self.manifest, self.records), before)

    def test_control_suffixes_cannot_be_laundered_by_reanchoring(self):
        for location in ('packet', 'manifest', 'artifact'):
            for suffix in ('\n', '\r', '\t', '\x00', '\x1f', '\x7f', '\x85', '\u2028', '\u2029'):
                with self.subTest(location=location, suffix=repr(suffix)):
                    self.setUp()
                    self.subject(location)['id'] += suffix
                    self.anchor()
                    with self.assertRaises(PacketError):
                        self.check()

    def test_valid_neighbor_identifiers_are_accepted_when_reanchored(self):
        for location in ('packet', 'manifest', 'artifact'):
            with self.subTest(location=location):
                self.setUp()
                self.subject(location)['id'] += ':neighbor_2-0.1'
                self.anchor()
                self.assertEqual(self.check(), 'unresolved')

    def test_large_exact_positive_revisions_remain_consistent(self):
        for location in ('manifest', 'artifact'):
            for revision in REVISIONS:
                with self.subTest(location=location, revision=revision):
                    self.setUp()
                    self.subject(location)['revision'] = revision
                    self.packet['manifest']['revision'] = self.manifest['revision']
                    self.anchor()
                    self.assertEqual(self.check(), 'unresolved')

    def test_adjacent_revisions_are_not_equal(self):
        for location in ('manifest', 'artifact'):
            for revision in REVISIONS:
                for delta in (-1, 1):
                    with self.subTest(location=location, revision=revision, delta=delta):
                        self.setUp()
                        self.subject(location)['revision'] = revision
                        self.packet['manifest']['revision'] = self.manifest['revision']
                        self.anchor()
                        if location == 'manifest':
                            self.packet['manifest']['revision'] += delta
                        else:
                            self.manifest['artifacts'][0]['revision'] += delta
                            self.packet['artifacts'][0]['revision'] += delta
                        with self.assertRaises(PacketError):
                            self.check()
