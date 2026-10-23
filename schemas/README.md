# Draft pipeline contracts

`v0.1/` is a **proposal**, version `catalog-pipeline-draft-0.1.0`.
It is independent of the research repository's frozen builder contract 1.0.0.
No consumer adoption or real-data publication follows from these schemas.

The draft illustrates entity identity, field-level claims, source/use decisions,
and immutable release metadata across multiple research domains. Schemas reject
unknown properties so accidental fields require an explicit reviewed change.
The example validator adds reference, rights-scope and synthetic-boundary checks
that JSON Schema alone cannot establish.

All initial examples are synthetic and use fictional identities and reserved
`example.invalid` URLs. They are never fetched. Real source material, rights
decisions, review receipts, signatures and consumer approvals require the future
implementation work and accepted authority in the backlog.

`planning/` validates repository planning files, not catalog records. A Project
field such as Evidence Confidence is a summary of a work item and is not the
claim-level evidence grade in the catalog contract.

Run `python scripts/validate_examples.py` after installing
`requirements-validation.txt`. The validator is an offline bootstrap check,
not a production policy engine, cryptographic signature verifier or publisher.
