# Catalog Pipeline charter

## Mission

Provide a shared, auditable path from permitted AI research inputs to normalized, evidence-linked, reviewed and reproducible catalog releases for Pick Your AI consumers. The implementation supports the organization-wide research ecosystem rather than treating language-model listings as its permanent scope.

The originating finding is [research #509, G04](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509). This charter records the authorized implementation-planning boundary. It does not reopen completed research, transfer another repository's ownership, approve a source, or authorize production deployment.

## Why this repository exists

Research records, policy decisions and consumer applications have different lifecycles from a recurring acquisition and publication service. The pipeline requires its own contracts, repeatable jobs, review controls, release identity, freshness monitoring, rollback and correction handling, consumer delivery, operational evidence and implementation backlog.

This boundary is useful only while shared machinery is implemented here and domain research remains authoritative upstream. New domain repositories must not fork the source-policy engine or maintain competing published identities for the same entity.

## In scope

| Area | Intended outcome |
| --- | --- |
| Source governance | Registered sources, material/use decisions, conditions, notices, restrictions, changes and revocation history |
| Acquisition | Permitted connectors with bounded retrieval, checkpoints, rate limits, replay, isolation and observable failures |
| Identity and normalization | Stable entity identities, aliases, exact revisions, typed claims, units, relationships, deduplication and reversible decisions |
| Evidence and review | Claim-level provenance, confidence and evidence class, conflict retention, human review and attributable decisions |
| Catalog and price storage | Versioned records and histories, separate pricebooks, exact references, corrections, withdrawals and reproducible projections |
| Publication | Explicit eligibility checks, immutable manifests, integrity and provenance receipts, atomic release promotion and retained history |
| Freshness | Changed-source detection, scope-aware rechecks, current-state disclosures and downstream invalidation |
| Consumer delivery | Versioned snapshots, API/export boundaries, compatibility checks, attribution, rights-aware projections and receiving receipts |
| Operations | Access control, security, observability, budgets, recovery, incident response and evidence of operational readiness |
| Coverage | Measurable breadth, gaps, unknowns and quality across the organization's research domains |

## Domain breadth

The coverage model must address models and providers; hosted offerings and pricing; accelerators, mobile/edge devices and runtimes; datasets and benchmark suites; measured evaluations and resource evidence; end-user applications and services; agents, MCP servers, tools, integrations and memory; papers, methods, authors and institutions; domain use cases; trust, security and governance attributes; and conditioned cost, energy and sustainability evidence.

Coverage denotes an explicit denominator and quality state. Merely adding an entity-kind name or scraping a large number of rows does not establish completeness. A domain may remain proposed, unavailable, unassessed, rights-restricted or unqualified while the architecture still supports it.

The builder's existing 29 component kinds remain a separate consumer contract. Broader ecosystem records do not become builder selections automatically.

## Exclusions

The pipeline does not own primary research acceptance, shared compatibility-policy decisions, user demand validation, the public website, native client UI, contributor recognition, nonprofit funding strategy, paid benchmarking campaigns, or separate scholarly/application/dataset editorial programs. It may consume their accepted outputs and provide exact delivery mechanisms.

The [accepted shared-service placement](https://github.com/Pick-Your-AI/pick-your-ai-android/blob/main/docs/SERVICE_BASELINE.md) identifies the website's `services/planner-api` lane for the future builder API. The catalog pipeline does not replace that placement or duplicate its build storage, evaluation, authentication or cost-estimation responsibilities. Its independent runtime and publication boundaries must be reviewed against that existing service contract.

Bootstrap creates planning and tooling foundations. It does not establish paid source access, permission to copy public pages, commercial data clearance, production hosting, a support commitment, or regulatory suitability of a listed product.

## Success measures

Success requires evidence at each stage:

1. **Bootstrap:** the repository foundation, stable hierarchical plan, decision and coverage registers, meaningful validation, and intended GitHub setup are coherent. Actual GitHub resources and settings are reported only after readback.
2. **Permitted pilot:** a bounded real source/material/use is accepted, ingestion is reproducible, field provenance and unknowns survive normalization, and review prevents an ineligible record from publication.
3. **Consumer delivery:** an exact immutable release is received and checked by a named consumer against an accepted version and use scope, including rejection, correction and revocation cases.
4. **Operational release:** authorized operators, measured performance and costs, accepted recovery objectives, incident procedures, security controls and rollback exercises are evidenced.
5. **Broader coverage:** each added domain has an approved identity/claim model, responsible research source, rights boundary, bounded coverage target and qualified consumer behavior.

No numerical SLO, capacity target, recurring budget or coverage percentage is implied until its decision is accepted. Track proposed and approved values separately.

## Governance and sources of truth

The [governance policy](GOVERNANCE.md) defines responsibility and completion. Native GitHub Assignees indicate accepted personal ownership; the initial plan leaves work unassigned where no acceptance exists. Team access and review settings require verification.

`planning/project-backlog.json` owns local implementation scope and decomposition. `planning/decision-register.json` owns proposed and accepted local decisions with their evidence. `planning/release-manifest.json` describes the bootstrap/release boundary. `planning/coverage-matrix.json` records scope coverage and gaps. GitHub issue and Project readbacks describe execution state; neither generated Markdown nor a proposed manifest substitutes for them.

The parent [research audit](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509) remains broader than this repository and cannot be closed solely by bootstrap completion.
