"""Synthetic inventory conservation and rejection behavior."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from src.metrics.coverage import CoverageError, report, report_bytes


def sid(label):
    return 'urn:pya:synthetic:' + label


def root(label='one', kind='entity', stage='candidate', exclusion='active'):
    return dict(id=sid(label), domain=sid('domain'), logical_id=sid(label),
                kind=kind, relation='canonical', stage=stage, exclusion=exclusion,
                rights='permit_fixture', evidence_class='Primary documentation',
                review_state='source_checked',
                freshness='unknown', consumer='not_received', missing_fields=[],
                maintenance={'state': 'unknown'})


def ledger(rows=None):
    return dict(schema_version='coverage-ledger-synthetic-0.2', synthetic=True,
                publication_eligible=False, domains=[dict(id=sid('domain'),
                inclusion_rule='explicit_fixture_members', scope_state='unknown_scope',
                denominators={k: {'state': 'unknown'}
                              for k in ('entity', 'release', 'offering', 'evidence')})],
                records=[root()] if rows is None else rows)


def wire(data):
    return json.dumps(data).encode()


def bucket(data, kind='entity'):
    return report(wire(data))['domains'][0]['units'][kind]


class CoverageTests(unittest.TestCase):
    def rejects(self, data):
        with self.assertRaises(CoverageError):
            report(wire(data))

    def test_all_stage_prefixes_conserve(self):
        stages = ('candidate', 'normalized', 'reviewed', 'eligible', 'published')
        rows = [root('item-' + str(i), stage=s) for i, s in enumerate(stages)]
        unit = bucket(ledger(rows))
        self.assertEqual(list(unit['simulated_stage_counts'].values()), [5, 4, 3, 2, 1])
        self.assertEqual(sum(unit['stage_drop_counts'].values()) +
                         unit['simulated_stage_counts']['published'], 5)
        self.assertEqual(set(unit['active_terminal_counts'].values()), {1})

    def test_aliases_and_merges_add_no_canonical_units(self):
        row = root(stage='published')
        alias = {k: row[k] for k in ('domain', 'kind', 'logical_id')}
        alias.update(id=sid('alias'), relation='alias', target=row['id'])
        merged = dict(alias, id=sid('merged'), relation='merged')
        unit = bucket(ledger([row, alias, merged]))
        self.assertEqual((unit['candidate_rows'], unit['canonical_units'],
                          unit['aliases'], unit['merged']), (3, 1, 1, 1))
        self.assertEqual(unit['simulated_stage_counts']['published'], 1)

    def test_exclusions_preserve_history_but_cannot_inflate_current(self):
        rows = [root('a', stage='published'),
                root('q', stage='reviewed', exclusion='quarantined'),
                root('w', stage='published', exclusion='withdrawn')]
        unit = bucket(ledger(rows))
        self.assertEqual(list(unit['simulated_stage_counts'].values()), [3, 1, 1, 1, 1])
        self.assertEqual(unit['historical_simulated_stage_counts']['published'], 2)
        self.assertEqual(sum(unit['exclusions'].values()), unit['canonical_units'])
        self.assertEqual(unit['stage_drop_counts']['candidate_to_normalized'], 2)

    def test_kinds_never_collapse_into_one_coverage_percentage(self):
        data = ledger([root(k, kind=k, stage='published')
                       for k in ('entity', 'release', 'offering', 'evidence')])
        result = report(wire(data))
        for unit in result['domains'][0]['units'].values():
            self.assertEqual(unit['canonical_units'], 1)
            self.assertEqual(unit['published_fixture_ratio'], {'state': 'unknown_denominator'})
            self.assertEqual(unit['completeness'], 'not_established')
        self.assertFalse(result['publication_eligible'])
        self.assertFalse(result['rights_cleared'])

    def test_exact_ratio_and_zero_and_unknown_are_distinct(self):
        data = ledger([root(stage='published')])
        denoms = data['domains'][0]['denominators']
        denoms['entity'] = dict(state='bounded_fixture', count=3, evidence_ref=sid('basis'))
        denoms['release'] = dict(state='bounded_fixture', count=0, evidence_ref=sid('basis'))
        self.assertEqual(bucket(data)['published_fixture_ratio'],
                         dict(state='exact_fixture_ratio', numerator=1, denominator=3))
        self.assertEqual(bucket(data, 'release')['published_fixture_ratio']['state'], 'empty_scope')
        self.assertEqual(bucket(data, 'offering')['published_fixture_ratio']['state'], 'unknown_denominator')

    def test_denominator_requires_evidence_and_cannot_hide_candidates(self):
        for count in (0, True, -1, 100000001):
            data = ledger()
            data['domains'][0]['denominators']['entity'] = dict(
                state='bounded_fixture', count=count, evidence_ref=sid('basis'))
            self.rejects(data)
        data = ledger()
        data['domains'][0]['denominators']['entity'] = dict(state='bounded_fixture', count=10)
        self.rejects(data)

    def test_quality_axes_missing_fields_and_unknown_cost_are_separate(self):
        a = root('a'); a.update(rights='unknown', evidence_class='Vendor claim',
                              missing_fields=['evidence', 'conditions'])
        b = root('b'); b['maintenance'] = dict(state='known_fixture', units=7)
        unit = bucket(ledger([a, b]))
        self.assertEqual(unit['quality']['rights'], {'permit_fixture': 1, 'unknown': 1})
        self.assertEqual(unit['missing_fields']['evidence'], 1)
        self.assertEqual(unit['maintenance'], dict(known_fixture_units=7, unknown_units_records=1))
        self.assertEqual(unit['quality']['freshness'], {'unknown': 2})

    def test_duplicate_logical_identity_is_not_silently_counted(self):
        a = root(); b = root('different'); b['logical_id'] = a['logical_id']
        self.rejects(ledger([a, b]))
        self.rejects(ledger([a, deepcopy(a)]))

    def test_duplicate_target_must_be_direct_same_domain_kind_and_identity(self):
        a = root(); alias = {k: a[k] for k in ('domain', 'kind', 'logical_id')}
        alias.update(id=sid('alias'), relation='alias', target=a['id'])
        for field, value in [('target', sid('absent')), ('target', alias['id']),
                             ('kind', 'release'), ('logical_id', sid('other'))]:
            changed = dict(alias); changed[field] = value
            self.rejects(ledger([a, changed]))
        second = dict(alias, id=sid('second'), target=alias['id'])
        self.rejects(ledger([a, alias, second]))

    def test_unknown_domains_and_duplicate_domains_reject(self):
        data = ledger(); data['records'][0]['domain'] = sid('absent'); self.rejects(data)
        data = ledger(); data['domains'].append(deepcopy(data['domains'][0])); self.rejects(data)

    def test_invalid_stages_and_missing_review_or_rights_reject(self):
        for stage in ('eligible', 'published'):
            for field, value in [('rights', 'unknown'), ('rights', 'deny'), ('evidence_class', 'unknown')]:
                a = root(stage=stage); a[field] = value; self.rejects(ledger([a]))
        a = root(stage='reviewed'); a['missing_fields'] = ['identity']; self.rejects(ledger([a]))
        a = root(); a['stage'] = 'accepted'; self.rejects(ledger([a]))

    def test_grade_and_source_check_histograms_are_independent(self):
        grades = ('Primary documentation', 'Vendor claim', 'Independent measurement', 'Estimate')
        states = ('unknown', 'source_checked', 'reviewed', 'independently_reproduced')
        rows = []
        for i, grade in enumerate(grades):
            for j, state in enumerate(states):
                row = root('grade-' + str(i) + '-' + str(j))
                row.update(evidence_class=grade, review_state=state)
                rows.append(row)
        quality = bucket(ledger(rows))['quality']
        self.assertEqual(quality['evidence_class'], {g: 4 for g in grades})
        self.assertEqual(quality['review_state'], {s: 4 for s in states})
        self.assertNotIn('evidence', quality)
        for field, value in [('evidence_class', 'source_checked'),
                             ('review_state', 'Vendor claim')]:
            row = root()
            row[field] = value
            self.rejects(ledger([row]))
        row = root()
        del row['review_state']
        self.rejects(ledger([row]))
        old = ledger()
        old['schema_version'] = 'coverage-ledger-synthetic-0.1'
        legacy = old['records'][0]
        del legacy['evidence_class'], legacy['review_state']
        legacy['evidence'] = 'source_checked'
        self.rejects(old)

    def test_excluded_rows_preserve_history_after_current_clearance_changes(self):
        changes = (
            {'rights': 'deny'},
            {'evidence_class': 'unknown', 'review_state': 'unknown'},
            {'missing_fields': ['rights', 'evidence']},
        )
        rows = []
        for i, exclusion in enumerate(('quarantined', 'withdrawn')):
            for j, changed in enumerate(changes):
                row = root('excluded-' + str(i) + '-' + str(j),
                           stage='published', exclusion=exclusion)
                row.update(changed)
                rows.append(row)
        unit = bucket(ledger(rows))
        self.assertEqual(unit['historical_simulated_stage_counts']['published'], 6)
        self.assertEqual(list(unit['simulated_stage_counts'].values()), [6, 0, 0, 0, 0])
        self.assertEqual(unit['quality']['rights'], {'deny': 2, 'permit_fixture': 4})
        self.assertEqual(unit['quality']['evidence_class'],
                         {'unknown': 2, 'Primary documentation': 4})
        self.assertEqual(unit['quality']['review_state'], {'unknown': 2, 'source_checked': 4})
        self.assertEqual(unit['missing_fields']['rights'], 2)
        self.assertEqual(unit['stage_drop_counts']['candidate_to_normalized'], 6)
        for row in rows:
            self.rejects(ledger([dict(row, exclusion='active')]))
            self.rejects(ledger([dict(row, consumer='received_fixture')]))

    def test_consumer_delivery_cannot_bypass_stage_or_withdrawal(self):
        for stage, exclusion in [('candidate', 'active'), ('published', 'withdrawn')]:
            a = root(stage=stage, exclusion=exclusion)
            a['consumer'] = 'received_fixture'; self.rejects(ledger([a]))
        a = root(stage='published'); a['consumer'] = 'received_fixture'
        self.assertEqual(bucket(ledger([a]))['quality']['consumer'], {'received_fixture': 1})

    def test_synthetic_and_integer_spoofing_and_unknown_fields_reject(self):
        for field, value in [('synthetic', False), ('synthetic', 1),
                             ('publication_eligible', True), ('publication_eligible', 0),
                             ('secrets', 'not-allowed')]:
            data = ledger(); data[field] = value; self.rejects(data)
        for value in (True, -1, 100000001):
            a = root(); a['maintenance'] = dict(state='known_fixture', units=value)
            self.rejects(ledger([a]))

    def test_strict_json_byte_and_collection_bounds(self):
        for payload in [b'', b' '*65537, b'\xff', b'{"x":1,"x":2}',
                        b'{"x":NaN}', b'{"x":1.1}', b'{"x":1234567890}',
                        b'['*2000 + b']'*2000, '{}', {}, bytearray(b'{}')]:
            with self.assertRaises(CoverageError): report(payload)
        self.rejects(ledger([root(str(i)) for i in range(129)]))
        data = ledger(); data['domains'] *= 17; self.rejects(data)

    def test_identifier_controls_nonreserved_values_and_public_sanitization(self):
        for value in [sid('one')+'\n', sid('one')+'\x7f', 'https://secret.invalid', sid('a/b')]:
            data = ledger(); data['records'][0]['id'] = value; self.rejects(data)
        payload = wire(ledger())
        output = report_bytes(payload)
        self.assertEqual(output, report_bytes(payload))
        self.assertNotIn(b'urn:', output)
        self.assertNotIn(b'logical_id', output)
        self.assertNotIn(b'complete_all', output)
        invalid = ledger(); invalid['private-secret'] = 'PRIVATE-CANARY'
        try: report(wire(invalid))
        except CoverageError as exc:
            self.assertEqual(str(exc), 'invalid_ledger')
            self.assertIsNone(exc.__context__)

    def test_all_stage_exclusion_combinations_conserve_independently(self):
        stages = ('candidate', 'normalized', 'reviewed', 'eligible', 'published')
        rows = [root('item-' + str(i*3+j), stage=stage, exclusion=exclusion)
                for i, stage in enumerate(stages)
                for j, exclusion in enumerate(('active', 'quarantined', 'withdrawn'))]
        unit = bucket(ledger(rows))
        current = unit['simulated_stage_counts']
        self.assertEqual([current[s] for s in stages], [15, 4, 3, 2, 1])
        self.assertEqual([unit['historical_simulated_stage_counts'][s]
                          for s in stages], [15, 12, 9, 6, 3])
        self.assertEqual(sum(unit['active_terminal_counts'].values()) +
                         unit['exclusions']['quarantined'] +
                         unit['exclusions']['withdrawn'], 15)
        self.assertEqual(sum(unit['stage_drop_counts'].values()) + current['published'], 15)

    def test_json_decodable_nested_duplicates_reject_without_recursion_leak(self):
        nested = []
        for _ in range(500):
            nested = [nested]
        data = ledger()
        data['records'][0]['missing_fields'] = [nested, nested]
        payload = wire(data)
        self.assertLess(len(payload), 65536)
        self.assertIsInstance(json.loads(payload), dict)
        with self.assertRaises(CoverageError) as caught:
            report(payload)
        self.assertEqual(str(caught.exception), 'json_limits')
        self.assertIsNone(caught.exception.__context__)

    def test_decoded_node_limit_precedes_schema_recursion(self):
        data = ledger()
        data['records'][0]['missing_fields'] = [[] for _ in range(8200)]
        payload = wire(data)
        self.assertLess(len(payload), 65536)
        with self.assertRaises(CoverageError) as caught:
            report(payload)
        self.assertEqual(str(caught.exception), 'json_limits')
        self.assertIsNone(caught.exception.__context__)

    def test_schema_recursion_defense_raises_fixed_context_free_error(self):
        with patch('src.metrics.coverage.Draft202012Validator') as validator:
            validator.return_value.is_valid.side_effect = RecursionError('PRIVATE-CANARY')
            with self.assertRaises(CoverageError) as caught:
                report(wire(ledger()))
        self.assertEqual(str(caught.exception), 'invalid_ledger')
        self.assertIsNone(caught.exception.__context__)

    def test_empty_inventory_is_zero_not_evidence_of_completeness(self):
        unit = bucket(ledger([]))
        self.assertEqual(unit['canonical_units'], 0)
        self.assertEqual(unit['completeness'], 'not_established')


if __name__ == '__main__':
    unittest.main()
