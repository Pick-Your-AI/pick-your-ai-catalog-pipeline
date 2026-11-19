# Offline draft contract conformance

Refs [CP-15.01, issue #73](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/73).
This is a partial conformance contribution against the separate catalog draft
`catalog-pipeline-draft-0.1.0`. It does not adopt or change frozen builder v1.

`tests/test_contract_conformance.py` exercises the committed draft schemas through
`scripts/validate_examples.py`. All generated records, claims, grants and receipts
are explicitly fictional. Tests write only to temporary local fixture directories;
they fetch no source, call no provider and publish no artifact.

## Covered behavior

| Boundary | Verification |
| --- | --- |
| Domain envelopes | A complete synthetic packet for each of the 27 currently declared kinds passes the existing offline validator, then fails when its evidence basis is removed, even after its artifact hash and scoped grant are updated. |
| Contract versions | Every registered example document rejects unsupported wire versions. |
| Typed values | Integer zero, Boolean false and exact decimal strings stay valid; coercible strings, wrong types and malformed decimal spellings fail. Known values cannot carry an unknown reason or omit their value; unknowns require a nonempty explanation. |
| Extensions | Undeclared publication authority fields fail at record, claim, evidence and source levels. |
| Relationship shape | References require a catalog URN, declared relation and positive exact revision; URL aliases, absent revisions and implicit compatibility relations fail. |
| Bootstrap identity | Every example document rejects missing/false synthetic labeling or an unqualified record identity. |
| Synthetic release boundary | Fictional approvals, signature text and publication eligibility cannot qualify a synthetic release. |
| Packet references | Wrong artifact revisions, missing/duplicate artifact entries and unpinned rights decisions produce explicit diagnostics. Duplicate claim identities and paths fail. |

The domain cases check the common claim envelope. Their field names and fictional
values do not establish domain-specific semantic rules, measured capabilities,
source rights or builder compatibility. No production signing path is exercised.
Schema acceptance of an object is separate from its admission as a bootstrap
fixture and from permission to use any real material.

## Run

The existing read-only CI workflow discovers this module without configuration
changes. Use the repository's Python 3.12 validation environment:

```bash
python scripts/validate_plan.py
python scripts/validate_examples.py
python scripts/render_docs.py --check
python -m unittest discover -s tests -v
git diff --check
```

For focused local iteration:

```bash
python -m unittest discover -s tests -p test_contract_conformance.py -v
```

## Remaining acceptance

Issue #73 remains open. These checks do not implement the full source-rights
registry or qualify an actual review identity, receiving handoff or production
release. The draft relationship schema checks reference shape; graph target
existence, target revision resolution and kind compatibility still need an
admission implementation and meaningful rejection tests under CP-07.01. Likewise,
these scenarios cannot establish empirical research #61/#62 qualification.
Independent eligible review of the exact latest push and the required CI check
remain necessary. Local passing tests are offline conformance evidence only.
