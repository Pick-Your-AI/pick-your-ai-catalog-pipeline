# Synthetic coverage ledger draft

Refs #36 (CP-07.04), partial offline engineering. This separately versioned draft
is independent of `planning/coverage-matrix.json`, which remains a planning source.
It does not measure a real catalog, authenticate decisions, grant rights or establish
complete bounded-domain coverage. Keep #36 open.

`src.metrics.coverage.report(payload)` accepts strict UTF-8 JSON **bytes** under
`schemas/coverage-ledger.schema.json`. `report_bytes` returns deterministic ASCII
JSON. The module only reads its fixed local schema. It performs no network request,
source acquisition, database write, publication or consumer communication. Fixtures
are inline in `tests/test_coverage_ledger.py`; production inputs are unsupported.

Each domain declares an explicit fixture-member inclusion rule and whether broader
scope is unknown. Entity, release, offering and evidence units have separate
inventories and denominators. A bounded fixture denominator requires an integer
count and reserved evidence reference; unknown denominators stay unknown. A caller's
reference is not proof of an exhaustive inventory or research acceptance. Count zero
means an empty supplied scope, not unknown. A denominator smaller than its canonical
inventory is rejected. No all-domain sum or ecosystem-wide percentage is generated.

Each candidate row is either canonical, an alias or a merged duplicate. Aliases and
merges point directly to one canonical row of the same domain, kind and logical
identity. Dangling references, duplicate row IDs, duplicate canonical logical IDs,
indirect/cyclic targets and incompatible targets fail. This is a supplied snapshot
of identity decisions; it does not accept, authenticate, reverse or persist a merge.
The same identity can be a member of multiple domains; domain totals must not be
summed as distinct ecosystem entities.

A canonical row declares its greatest simulated stage. Its historical prefix runs
from candidate through normalized, reviewed, eligible and published. These are
fixture stages, never actual approvals or release receipts. Reviewed-or-later rows
cannot declare missing mandatory fields. Eligible/published rows require fixture
permission and non-unknown evidence, without converting either into real clearance.
A current received-fixture flag requires an active published-fixture row.

Reports retain historical stage counts separately from current simulated counts.
Quarantined and withdrawn canonical rows stay in candidate inventory and historical
counts, but contribute to no current stage beyond candidate. Thus:

- Candidate rows = canonical units + alias rows + merged rows.
- Canonical units = active + quarantined + withdrawn units.
- Current stage counts never increase down the stage sequence.
- Every current stage drop plus current published count reconciles to candidate
  canonical units. The first drop includes excluded units and active candidate-only
  units; other drops represent active units whose greatest stage is the earlier one.

Rights, evidence, freshness and receiving-state histograms cover canonical units,
including exclusions, and stay separate from stage counts. Missing mandatory-field
counts expose depth gaps. Maintenance uses exact fixture work units, never money or
elapsed production cost; unknown work is counted separately rather than zero-filled.
An exact published-fixture fraction is emitted as integer numerator/denominator only
when a nonzero bounded denominator is supplied. Every bucket still declares
`completeness=not_established`. No fraction proves source truth, independently
reproduced evidence, receiving acceptance or global AI completeness.

Only synthetic reserved IDs and fixed enums are admitted. Public reports omit all
input IDs, evidence references, URLs and caller prose, using domain ordinals and
fixed labels. Errors use fixed codes, with parse/validation errors raised outside
exception handlers to avoid attaching a raw-input exception context. Report contents
remain `synthetic_unverified`, `rights_cleared=false` and
`publication_eligible=false`, even for simulated published rows.

Input is bounded to 64 KiB, decoded depth 12 (root depth zero), 8,192 decoded
value nodes, 16 domains, 128 candidate rows, short reserved identifiers and integer fields between zero and 100,000,000. JSON integer literals are at most
nine characters; decimals, nonfinite numbers, duplicate keys and invalid UTF-8 fail.
Decoded depth/node checks run iteratively before schema validation; a defensive
schema-recursion guard also produces a fixed context-free rejection. These are
admission limits, not a CPU, sandbox or production memory guarantee.
Schema validation alone does not check reference integrity, stage dependencies or
denominator consistency; consumers must use the runtime validator as well.

Run `python -m unittest discover -s tests -p test_coverage_ledger.py -v` for focused
synthetic conservation, deduplication, exclusion, quality and rejection checks.
Actual accepted CP-01.01, CP-05.02 and CP-07.02 outcomes, authenticated record/review/
rights lineage, accepted bounded denominators, real maintenance evidence and receiving
receipts remain absent. Independent review and a permitted exact-main integration
remain required. Rollback removes the four new files; no accepted contract or stored
production data is migrated.
