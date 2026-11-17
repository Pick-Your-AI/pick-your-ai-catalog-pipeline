# Offline audit-chain primitive

This is a partial implementation for [CP-06.04, issue #31](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/31).
It provides bounded, network-free and filesystem-free append/verify functions.
It is not a production audit ledger. No actor, rights, review, identity or
publication decision is authenticated or authorized by hashing its bytes.

`src/audit/chain.py` accepts strict UTF-8 JSON **object bytes**, retaining the
exact event and affected-object bytes. Formatting and key-order changes inside
those bytes change their hashes. It rejects duplicate JSON keys, trailing data,
invalid Unicode, nonfinite numbers and all floating-point/exponent tokens.
Represent exact decimal quantities as explicit strings; integers retain up to
128 decimal digits. This module gives JSON null/boolean values no new meaning
and does not fill absent fields or interpret a submitted assertion as approval.

The private hash envelope namespace is `pya-offline-audit-envelope-v1`. Its
encoding uses Python JSON with sorted keys, ASCII escaping and compact separators.
Affected-object IDs sort by Python string code-point order. The envelope binds
the external chain ID, one-based sequence, prior digest, exact event SHA-256 and
every affected-object ID/content SHA-256. This is a versioned local encoding,
not a claim of standard cross-language JSON canonicalization. Changing encoding
requires a separately reviewed namespace/migration decision.

Both `verify` and `append` require `chain_id`, `expected_head` and
`expected_count`. Those values must come from a separately trusted checkpoint.
`empty_head(chain_id)` identifies an empty chain. Verification checks the entire
snapshot, its ordered sequence and exact final head/count. Missing, inserted,
replayed, reordered, modified and truncated entries fail against the retained
original checkpoint. A completely recomputed replacement chain can be internally
consistent: supplying its own new head/count does **not** authenticate it.
Checkpoint custody, freshness and rollback protection are outside this module.

For example, these are synthetic bytes and locally computed checksums only:

```python
from src.audit.chain import append, empty_head, verify

chain_id = "urn:pya:synthetic:audit:example"
snapshot = append(
    (), chain_id=chain_id, expected_head=empty_head(chain_id), expected_count=0,
    event=b'{"id":"urn:pya:synthetic:event:example","state":"attempted"}',
    affected_objects={"urn:pya:synthetic:claim:example": b'{"value":"unknown"}'},
)
# An application must protect this checkpoint independently before relying on it.
head, count = snapshot[-1].digest, len(snapshot)
verify(snapshot, chain_id=chain_id, expected_head=head, expected_count=count)
```

Snapshots are tuples of frozen entries, immutable bytes and tuples of object
ID/bytes pairs. Appending returns a new snapshot and preserves every earlier
snapshot. Mutating the caller's original dictionary cannot rewrite retained
objects. Verification still validates entry types and content because a caller
can construct replacement entries. Python object immutability is not an access
control or a defense against arbitrary code executing in the same process.
Identical event bytes may be intentionally recorded in another append; semantic
duplicate-event/idempotency policy is not supplied here. Unexpected replay fails
only relative to the separately retained sequence/head/count checkpoint.

Bounds are 1,024 events, 16,384 bytes per JSON value, 32 affected objects per event,
depth 16 (root depth zero), 2,048 parsed nodes including object keys, and 1,048,576
total retained event/object-content and object-ID UTF-8 bytes. Identifiers have a
256-byte limit and reject control characters. Mutable Python dictionaries,
recursive object graphs and bytearrays cannot be submitted as JSON event bytes.
Append verifies the full prior snapshot, so it has linear cost per append and
is deliberately unsuitable as an unbounded storage engine. Limits reject input;
they are not process-isolation, concurrency or resource-exhaustion guarantees.

Issue #31 remains open. Its missing work includes the accepted audit-event schema
and correction semantics; actual actor identity/authority and separation of
planned, attempted, accepted and released actions; integration with provenance,
rights, review, identity and publication decisions; effective intervals, reasons
and supersession that preserve earlier failed/withdrawn evidence; durable atomic
persistence and trusted checkpoint custody; access, retention, privacy projection
and permitted restricted-content deletion rules; and crash/recovery behavior.
This in-memory primitive retains affected bytes, so callers must not submit
restricted or personal material without separately accepted retention authority.
Actual affected-owner/independent reviews and exact integration/consumer receipts
remain required. CP-06.01 and CP-01.02 acceptance is not inferred. Synthetic
tampering tests prove only bounded local rejection behavior, not real rights,
signed history, operational custody or deployed recovery.
