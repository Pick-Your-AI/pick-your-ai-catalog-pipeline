"""Bounded synthetic coverage accounting; never a publication authorizer."""
from collections import Counter
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).resolve().parents[2] / 'schemas/coverage-ledger.schema.json'
STAGES = ('candidate', 'normalized', 'reviewed', 'eligible', 'published')
KINDS = ('entity', 'release', 'offering', 'evidence')
MAX_BYTES = 65536
MAX_DEPTH = 12
MAX_NODES = 8192


class CoverageError(ValueError):
    """Fixed trusted diagnostic, containing no caller strings."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _integer(value):
    if len(value) > 9:
        raise ValueError()
    return int(value)


def _noninteger(value):
    raise ValueError()



def _check_tree(data):
    # Iteration bounds malformed, JSON-decodable values before jsonschema may
    # compare them recursively (for example uniqueItems on nested arrays).
    pending = [(data, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise CoverageError('json_limits')
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)


def report(payload):
    """Validate strict JSON bytes and return a sanitized deterministic report.

    Candidate rows are an inventory, not authenticated events. Each canonical
    row supplies its greatest simulated stage; earlier stages are its prefix.
    Aliases/merged rows point directly to one canonical row and never add units.
    Excluded roots retain historical stages but contribute to no current stage
    beyond candidate. Report names explicitly label every count as simulated.
    """
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise CoverageError('invalid_payload')
    malformed = False
    try:
        data = json.loads(payload.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_int=_integer, parse_float=_noninteger,
                          parse_constant=_noninteger)
    except (ValueError, UnicodeError, RecursionError):
        malformed = True
    if malformed:
        raise CoverageError('invalid_json')
    _check_tree(data)
    schema = json.loads(SCHEMA.read_text())
    valid = False
    try:
        valid = Draft202012Validator(schema).is_valid(data)
    except RecursionError:
        pass  # Defense in depth; raise outside handler without input context.
    if not valid:
        raise CoverageError('invalid_ledger')
    domains = data['domains']
    if len({d['id'] for d in domains}) != len(domains):
        raise CoverageError('duplicate_domain')
    rows = data['records']
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows):
        raise CoverageError('duplicate_candidate')
    domain_ids = {d['id'] for d in domains}
    roots = [r for r in rows if r['relation'] == 'canonical']
    logical = set()
    for row in rows:
        if row['domain'] not in domain_ids:
            raise CoverageError('unknown_domain')
        if row['relation'] == 'canonical':
            key = (row['domain'], row['kind'], row['logical_id'])
            if key in logical:
                raise CoverageError('duplicate_logical_identity')
            logical.add(key)
            reached = STAGES.index(row['stage'])
            if reached >= 2 and row['missing_fields']:
                raise CoverageError('incomplete_review')
            if reached >= 3 and (row['rights'] != 'permit_fixture'
                                 or row['evidence'] == 'unknown'):
                raise CoverageError('ineligible_stage')
            if row['consumer'] == 'received_fixture' and (
                    row['stage'] != 'published' or row['exclusion'] != 'active'):
                raise CoverageError('inconsistent_delivery')
        else:
            target = by_id.get(row['target'])
            if target is None or target['relation'] != 'canonical':
                raise CoverageError('invalid_duplicate_target')
            if any(row[k] != target[k] for k in ('domain', 'kind', 'logical_id')):
                raise CoverageError('duplicate_identity_mismatch')
    output = []
    for ordinal, domain in enumerate(domains, 1):
        buckets = {}
        for kind in KINDS:
            selected = [r for r in roots if r['domain'] == domain['id'] and r['kind'] == kind]
            raw = [r for r in rows if r['domain'] == domain['id'] and r['kind'] == kind]
            active = [r for r in selected if r['exclusion'] == 'active']
            current = {s: sum(s == 'candidate' or (r['exclusion'] == 'active'
                       and STAGES.index(r['stage']) >= STAGES.index(s))
                       for r in selected) for s in STAGES}
            historical = {s: sum(STAGES.index(r['stage']) >= STAGES.index(s)
                                for r in selected) for s in STAGES}
            denominator = domain['denominators'][kind]
            if denominator['state'] == 'bounded_fixture':
                count = denominator['count']
                if count < len(selected):
                    raise CoverageError('denominator_below_inventory')
                ratio = ({'state': 'exact_fixture_ratio', 'numerator': current['published'],
                          'denominator': count} if count else {'state': 'empty_scope'})
            else:
                ratio = {'state': 'unknown_denominator'}
            costs = [r['maintenance']['units'] for r in selected
                     if r['maintenance']['state'] == 'known_fixture']
            buckets[kind] = {
                'candidate_rows': len(raw), 'canonical_units': len(selected),
                'duplicate_rows': len(raw) - len(selected),
                'aliases': sum(r['relation'] == 'alias' for r in raw),
                'merged': sum(r['relation'] == 'merged' for r in raw),
                'exclusions': {s: sum(r['exclusion'] == s for r in selected)
                               for s in ('active', 'quarantined', 'withdrawn')},
                'simulated_stage_counts': current,
                'historical_simulated_stage_counts': historical,
                'active_terminal_counts': {s: sum(r['stage'] == s for r in active) for s in STAGES},
                'stage_drop_counts': {STAGES[i] + '_to_' + STAGES[i+1]:
                                     current[STAGES[i]] - current[STAGES[i+1]]
                                     for i in range(len(STAGES)-1)},
                'quality': {axis: dict(sorted(Counter(r[axis] for r in selected).items()))
                            for axis in ('rights', 'evidence', 'freshness', 'consumer')},
                'missing_fields': {field: sum(field in r['missing_fields'] for r in selected)
                                   for field in ('identity', 'evidence', 'rights', 'conditions')},
                'maintenance': {'known_fixture_units': sum(costs),
                                'unknown_units_records': len(selected) - len(costs)},
                'published_fixture_ratio': ratio,
                'completeness': 'not_established',
            }
        output.append({'domain_ordinal': ordinal,
                       'inclusion_rule': domain['inclusion_rule'],
                       'scope_state': domain['scope_state'], 'units': buckets})
    return {'schema_version': 'coverage-report-synthetic-0.1', 'synthetic': True,
            'rights_cleared': False, 'publication_eligible': False,
            'evidence_status': 'synthetic_unverified', 'domains': output}


def report_bytes(payload):
    """Canonical ASCII report; no input IDs, locators or prose are reflected."""
    return json.dumps(report(payload), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')
