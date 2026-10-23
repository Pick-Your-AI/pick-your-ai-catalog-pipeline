# Research and consumer handoffs

## Purpose

A handoff identifies a producer artifact, its exact revision and permitted scope, the transformation or interface that consumes it, and the receiving evidence. It prevents a research proposal, policy decision, synthetic fixture or client test from being mistaken for a broader production approval.

The read-only bootstrap audit was performed on 2026-10-22. State summaries below are dated observations; refresh live issues, comments, revisions and owners before any new mutation or acceptance decision.

## Accepted upstream foundations

| Upstream entry point | Audited state | Reuse in the pipeline | Boundary |
| --- | --- | --- | --- |
| [Research #509](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509) | Open | G04 establishes the combined pipeline repository proposal; the broader audit supplies ecosystem coverage gaps | This repository does not close the entire research gap audit |
| [T0 #1](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/1), [T1 #4](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/4), [T2 #8](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/8), [T3 #12](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/12), [T4 #24](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/24), [T5 #29](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/29), [T6 #34](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/34) | Closed | Reviewed domain decisions, canonical mappings, evidence limitations and research artifacts | Do not clone completed research tasks or infer publication clearance |
| [Research #40](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/40) | Closed | Accepted contract and compatibility governance; frozen v1 adoption and successor review process | New pipeline entities and history do not silently change builder v1 |
| [Research #41](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/41) | Closed | Claim evidence grades, conflict policy, pinned/current-state distinction and source governance | No universal TTL, blanket source admission or independently verified grade from a simple fetch |
| [Research #39](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/39) | Closed | Price and cost semantics, exact versions, scope conditions and uncovered costs | No universal quote, zero-filled missing cost or unsupported meter disguised as an existing one |
| [Research #60](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/60) | Closed | Dated source/material/use decisions and restrictions | Closed research acceptance does not grant all uses of every source |
| [Research #61](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/61) | Open | Pinned runtime measurement requirements for GPU sizing | A pipeline parser does not perform or accept the measurement campaign |
| [Research #62](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/62) | Open | Benchmark comparability and harness-effect qualification | Vendor scores or external tables are not independently reproduced results |

Closed policy issues are accepted inputs. A new source, use, schema change or empirical claim may still need a specific decision under their accepted process. Reference that concrete decision or artifact rather than inventing a dependency on reopening the old issue.

## Canonical documents

- [Research contributor instructions](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/AGENTS.md)
- [Shared T0–T6 execution rules](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/prompts/SHARED.md)
- [Research method and evidence grades](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/RESEARCH_METHOD.md)
- [Research submission and validation workflow](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/RESEARCH_WORKFLOW.md)
- [Canonical kind mapping](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/CONTRACT_MAPPING.md)
- [Frozen builder contract adoption](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/contracts/v1/ADOPTION.md)
- [Source and freshness policy](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/research/T0-configuration/catalog-data-sources.md)
- [Publication eligibility handoff](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/PUBLICATION_ELIGIBILITY_HANDOFF.md)

Branch URLs are navigation entry points. Every actual import, claim decision or release receipt must pin the reviewed commit/artifact version and content digest where appropriate; a link to changing `main` is not an immutable receipt.

## Publication eligibility boundary

The existing handoff establishes no complete current catalog or pricebook as cleared for publication. Its historical inventory pins proposal bytes and source attribution but is not a live source-permission service.

For each real projection, resolve field-to-source attribution, material scope, retrieval permission, internal research use, public display, redistribution, required notices, conditions and any product restrictions. Preserve unclear or missing decisions and withhold affected operations. A record that cites both a permissive metadata registry and a restricted source cannot inherit the registry's permission for every field.

The current product decision excludes GPUs.io retrieval, display and export. Reconsideration requires a specific permitted-use basis and an accepted superseding #39/#41/#60-scope decision. No paid subscription or source acquisition is authorized by this bootstrap.

## Handoff packet

Every material producer/consumer handoff must identify:

1. Producer repository, issue or accepted decision, exact commit and artifact paths, artifact IDs/revisions, and hashes where used for identity.
2. Schema namespace/version, input and output types, cardinality, reference rules, transforms, dropped/unsupported fields and migration consequences.
3. Field/claim provenance, actual access/effective dates, source versions, units, regions, currencies, operating conditions, evidence class, confidence basis and unknowns.
4. Source/material/use decisions, notices, product scope, restrictions, expiry or change triggers if actually adopted, and correction/withdrawal behavior.
5. Intended consumer, exact release/projection, use purpose, accepted API/export scope, receiving tests, supported versions and rollback behavior.
6. Real reviewer/receiver identity, decision, timestamp, reviewed commit, scope, limitations and the linked receipt. A role placeholder or synthetic example is not acceptance.

Retain the previous and superseded packet when a decision changes. A successful hash comparison does not authenticate the reviewer or establish rights.

## Consumer responsibilities

| Consumer | Pipeline deliverable | Receiving requirement |
| --- | --- | --- |
| [Website](https://github.com/Pick-Your-AI/pick-your-ai-website) | Eligible immutable projection, provenance/attribution, price separation, revisions, corrections and public API/export use scope | Verify schema/version and artifact integrity; test unknown, stale/current-state, restricted-field, revocation and rollback behavior; accept exact display/redistribution use |
| [Apple](https://github.com/Pick-Your-AI/pick-your-ai-apple) | Versioned receiving contract, stable IDs, qualified data, revision/rights updates and offline/cache behavior | Keep app-owned conformance and receiving tests; reject incompatible or ineligible releases; demonstrate update, correction and offline limitations |
| [Android](https://github.com/Pick-Your-AI/pick-your-ai-android) | The shared release contract and Android-specific receiving envelope where required | Preserve shared service ownership; test exact versions and hash-bound artifacts; handle unknown capabilities, stale caches and rights changes explicitly |
| Future domain repositories | Registered producer artifact and domain-to-catalog mapping | Domain owner accepts identity, claims, rights, coverage and correction routing before admission |

Website, Apple and Android work remains in those repositories. Create a new client task only for a distinct missing receiving deliverable after checking existing planning. One client's receipt does not establish another client's acceptance. Runtime compatibility and deployment authorization remain separate from catalog ingestion.

### Existing receiving contracts and service placement

The website's [data integration seam](https://github.com/Pick-Your-AI/pick-your-ai-website/blob/main/docs/DATA_INTEGRATION.md) and [contract adoption](https://github.com/Pick-Your-AI/pick-your-ai-website/blob/main/contracts/v1/ADOPTION.md) are the first consumer references. Existing [website #15](https://github.com/Pick-Your-AI/pick-your-ai-website/issues/15), [#16](https://github.com/Pick-Your-AI/pick-your-ai-website/issues/16), [#17](https://github.com/Pick-Your-AI/pick-your-ai-website/issues/17) and [#18](https://github.com/Pick-Your-AI/pick-your-ai-website/issues/18) must be reconciled before opening overlapping integration work. Snapshot, pricebook, ruleset, dependency-graph and build-lock identities are distinct; preserve the exact tuple used by a consumer. A newer snapshot does not automatically invalidate a saved build.

Android's [contract adoption](https://github.com/Pick-Your-AI/pick-your-ai-android/blob/main/docs/CONTRACT_ADOPTION.md), [revision handoff](https://github.com/Pick-Your-AI/pick-your-ai-android/blob/main/docs/CONTRACT_REVISION_HANDOFF.md) and [service baseline](https://github.com/Pick-Your-AI/pick-your-ai-android/blob/main/docs/SERVICE_BASELINE.md) preserve the frozen contract and receiving requirements. [Android #35](https://github.com/Pick-Your-AI/pick-your-ai-android/issues/35) is the existing shared-service placement lane. Its accepted direction is one future TypeScript/Node API with managed PostgreSQL on Render, with canonical source in the website's `services/planner-api` lane. Operating acceptance remains separate. This pipeline supplies qualified artifacts; it does not create a duplicate builder/evaluation/authentication backend or authorize that paid deployment.

Apple's [repository scope](https://github.com/Pick-Your-AI/pick-your-ai-apple/blob/main/docs/REPOSITORY_SCOPE.md), [scoped research receiving decision](https://github.com/Pick-Your-AI/pick-your-ai-apple/blob/main/docs/decisions/research-inputs-20261018.md) and [conformance contract lock](https://github.com/Pick-Your-AI/pick-your-ai-apple/blob/main/tools/conformance/contract-lock.json) define its receiving baseline. [Apple #23](https://github.com/Pick-Your-AI/pick-your-ai-apple/issues/23) is the existing service integration lane. Preserve the exact imported bytes, source revision, schema version and expected historical behavior; old text describing #40 as open is historical and must not override the later closed research state.

The accepted [English kind-label sidecar](https://github.com/Pick-Your-AI/pick-your-ai-research/commit/d3548b303eaea7450615848db056f33f97d2cea6) is independent of frozen v1. A display-label change does not create a canonical kind, translation or new tier. Consumer import decisions must retain exact artifact bytes and checksums where required. Decimal price and numerical evidence boundaries must preserve exact values and strings rather than silently rounding through a different language's floating-point representation.

Frozen OpenAPI 1.0.0 applies global `bearerAuth`, including GET reads. Do not present an anonymous static mirror as implementing that authenticated contract. Public immutable artifacts require an independently accepted distribution channel or a reviewed contract change, and static distribution cannot implement write, evaluation or estimate operations. Missing current-catalog/resource-estimate endpoints and other API gaps require explicit versioned decisions.

## Synthetic pilot and real-data promotion

Bootstrap examples exercise proposed contracts and failure paths with fictional identities and claims. They must retain synthetic markings through every transform, manifest and receipt. The initial plan must not attach fabricated real owners, sources, prices, source grants or review decisions to those examples.

A later permitted real-data pilot requires an explicit bounded source/material/use, an accepted field mapping and contract, reviewable provenance, validation and rejection evidence, and a receiving consumer decision. Promotion must not copy an example's synthetic rights or acceptance fields into the real release.

## Completion

Producer research acceptance, pipeline implementation acceptance, consumer receiving acceptance and production release approval are separate. Record the exact scope of each receipt. A passing validator, merged PR or closed upstream issue does not automatically complete the other three.
