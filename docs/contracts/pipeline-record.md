# Pipeline record envelope draft

Refs [#8 (CP-02.01)](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/8).
The [pipeline record schema](../../schemas/pipeline-record.schema.json) defines
the independent synthetic wire version `catalog-pipeline-record-draft-0.1.0`.
The [fixture collection](../../examples/synthetic/entities.json) exercises
models, offerings, hardware, datasets, applications, tools, papers,
organizations, use cases, learning resources and the three benchmark roles.
This proposal keeps publication state at `withheld` and carries no consumer
mapping, accepted schema decision or source-use grant.

## Identity, versions and provenance

A record's logical `id` persists across its positive integer revisions.
`(id, revision)` identifies an exact record, including in relationship targets.
The fixture validator requires each pair to occur once and all relationship
targets to resolve to exact revisions in the collection. Integers are limited
to the range that can be represented exactly by common IEEE 754 consumers.
The schema recognizes a closed entity-kind set. Benchmark suites, runs and
results each have their own IDs and revisions. The example run points to its
suite and the result points to the run.

A provenance entry carries the source and material identifiers, source revision,
UTC observation time and reserved fixture locator. The collection validator
does not open source locators. Verified source custody, field-level evidence and
permission to publish remain separate decisions.

## Field states

| State | Meaning |
| --- | --- |
| Absent | The record makes no assertion about the field. |
| `known` | The record supplies a tagged text, integer, boolean or exact decimal value. |
| `unknown` | The value is relevant but the evidence does not establish it. |
| `unsupported` | This draft or the proposed mapping has no supported representation for the field. |
| `not_applicable` | The field is outside the scope of this particular record. |
| JSON `null` | Invalid for a field state or its value. Use the applicable explicit state. |

The three states without values require a reason. Zero and false are present
values. Decimals use strings to preserve scale. The fixture reader accepts
integer JSON tokens and rejects fractional or exponent tokens. This keeps
numeric value handling explicit at the wire boundary.

Field keys use dot-separated lowercase segments. Additional record properties
are rejected. The optional `extensions` map accepts only reserved
`example.invalid.<name>` namespaces and uses the same field-state rules.
Extensions add namespaced fixture fields. New kinds, state semantics or
published namespaces require an explicit contract decision and review.

## Frozen builder boundary

The builder contract stays canonical in the research repository. The
[adopted 1.0.0 import](https://github.com/Pick-Your-AI/pick-your-ai-research/tree/9769fcd9ea380b1211669b2753181c7782444178/contracts/v1)
was published in [Research PR #44](https://github.com/Pick-Your-AI/pick-your-ai-research/pull/44).
Its `contracts/v1` tree is `b1c4eaa4037f2a1e02103849064a947e758a2b40`.
The [import manifest](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/9769fcd9ea380b1211669b2753181c7782444178/contracts/v1/IMPORT_MANIFEST.json)
records the per-file SHA-256 hashes. The new fixtures carry their own version
and have no implicit migration or projection to the existing pipeline draft
or frozen builder v1.

Run `python scripts/validate_examples.py` and
`python -m unittest discover -s tests -p test_pipeline_record.py -v`.
Accepted [scope and ownership #3](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/3)
and independent producer and receiving review remain prerequisites for adopting the draft.
