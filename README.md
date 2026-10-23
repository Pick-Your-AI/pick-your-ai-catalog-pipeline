# Pick Your AI — Catalog Pipeline

Shared ingestion, source governance, normalization, evidence review, catalog publication, freshness, and consumer delivery for the Pick Your AI research ecosystem.

**Bootstrap status — 2026-10-23 04:54:13 UTC:** the foundation and bounded issue-graph workflow are published in the [public repository](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline), and hosted `ci-required` validation passed **100 tests**. All **81 canonical issues** have been published and audited. [Organization Project #8](https://github.com/orgs/Pick-Your-AI/projects/8) is public, has the requested title, description and **11 field definitions/options**, and contains all **81 issues**. Project values and eight saved views still need completion and readback. The native graph is verified complete: **81 native types, 80 internal parent links and 135 prerequisite links**. Team grants are blocked by GitHub's administrative reauthentication prompt, and branch-rule/check enforcement is not yet configured. [BOOTSTRAP_STATUS.md](docs/BOOTSTRAP_STATUS.md) and [execution-receipt.json](planning/execution-receipt.json) distinguish these verified results from pending work. The mission remains incomplete. No production ingestion, catalog release, or hosted service was deployed.

The public repository is `Pick-Your-AI/pick-your-ai-catalog-pipeline`, repository ID `1430404474`. The latest source revision verified for this snapshot is [`63c1c6e881ddaba817fb1c58a6a8e629ad85e33f`](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/commit/63c1c6e881ddaba817fb1c58a6a8e629ad85e33f), with [successful hosted validation](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/actions/runs/39900854598). The dedicated Project is [**Pick Your AI — Catalog Pipeline, #8**](https://github.com/orgs/Pick-Your-AI/projects/8); its actual number was observed after creation. The implementation program is [catalog pipeline #1](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/1). The canonical parent research finding remains [research #509, G04](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509), whose native cross-repository relationship still needs separate verification.

## Purpose

Turn permitted, attributable research inputs into versioned, reviewable records and reproducible consumer releases. The platform must support the entire AI research ecosystem: models and providers, hosted offerings, hardware and runtimes, datasets and evaluations, applications and services, agents and integrations, papers and methods, organizations, use cases, trust attributes, and conditioned cost evidence.

The system preserves the distinction between an observation, a normalized claim, a reviewed finding, a source-use decision, an eligible publication, and a consumer's accepted delivery. Unknowns remain explicit. A valid schema or a merged research proposal does not by itself establish truth, legal permission, freshness, or production readiness.

## Boundaries

| Responsibility | Canonical location |
| --- | --- |
| Research methods, accepted evidence/source policy, T0–T6 decisions, frozen builder v1 contracts | [pick-your-ai-research](https://github.com/Pick-Your-AI/pick-your-ai-research) |
| Shared acquisition, normalization, provenance, review gates, immutable releases, correction and delivery machinery | This repository |
| Public browsing, reference pages, search/filter UI, editorial presentation, accessibility and SEO | [pick-your-ai-website](https://github.com/Pick-Your-AI/pick-your-ai-website) |
| Native Apple and Android experiences and client receiving tests | [pick-your-ai-apple](https://github.com/Pick-Your-AI/pick-your-ai-apple), [pick-your-ai-android](https://github.com/Pick-Your-AI/pick-your-ai-android) |
| Contributor recognition | [pick-your-ai-leaderboard](https://github.com/Pick-Your-AI/pick-your-ai-leaderboard) |
| Funding and nonprofit sustainability research | [pick-your-ai-sustainability](https://github.com/Pick-Your-AI/pick-your-ai-sustainability) |

The new catalog contract is a separately versioned draft. It must not modify the research repository's frozen `contracts/v1/` bytes or silently extend its 29 builder kinds. Builder compatibility is delivered through reviewed projections and versioned handoffs. Source-specific research and broader domain repositories remain authoritative for their own findings.

The existing [shared service baseline](https://github.com/Pick-Your-AI/pick-your-ai-android/blob/main/docs/SERVICE_BASELINE.md) places the future builder API in the website's `services/planner-api` lane. This pipeline supplies qualified immutable artifacts to that service. It does not create a second user-build, evaluation, authentication or cost-estimation backend.

## Read the plan

- [Charter](docs/charter.md): purpose, scope, success measures, and exclusions.
- [Architecture](docs/ARCHITECTURE.md): proposed boundaries, data flow, failure handling, and contract design.
- [Delivery plan](docs/DELIVERY_PLAN.md): implementation hierarchy and sequencing.
- [Dependencies](docs/DEPENDENCIES.md): actual prerequisites versus informational handoffs.
- [Research handoffs](docs/RESEARCH_HANDOFFS.md): accepted inputs and required receiving evidence.
- [Governance](docs/GOVERNANCE.md): ownership, review, decisions, and completion rules.
- [Operations](docs/OPERATIONS.md): planned operational controls and release gates.
- [Project setup](docs/PROJECT_SETUP.md): intended Project configuration and verified execution state.

The machine-readable planning sources are [`planning/project-backlog.json`](planning/project-backlog.json), [`planning/decision-register.json`](planning/decision-register.json), [`planning/release-manifest.json`](planning/release-manifest.json), and [`planning/coverage-matrix.json`](planning/coverage-matrix.json). Generated documentation is a projection of those sources. Live GitHub issue state, native relationships, Assignees, and Project field values require independent readback.

## Validate the bootstrap

Use Python 3.12 from the repository root:

```bash
python -m pip install -r requirements-validation.txt
python scripts/validate_plan.py
python scripts/validate_examples.py
python scripts/render_docs.py --check
python -m unittest discover -s tests -v
```

To regenerate planning documentation after an intentional plan change:

```bash
python scripts/render_docs.py
```

These commands check local structure and consistency. They do not fetch source terms, verify empirical claims, approve rights, create GitHub resources, or establish consumer acceptance. Report actual results and any unexecuted checks; do not infer success from the presence of these commands.

## Data and publication

All initial files under [`examples/`](examples/) are explicitly **synthetic** and are unsuitable for real catalog publication. The initial release manifest must preserve that boundary. No current research proposal is automatically imported as cleared product data.

The research [publication eligibility handoff](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/PUBLICATION_ELIGIBILITY_HANDOFF.md) establishes no blanket permission for complete existing catalog or pricebook artifacts. Retrieval, internal use, commercial display, and redistribution require separate source/material/use decisions. Mixed-source records cannot inherit their most permissive source's rights.

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md), and the [organization contribution policy](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md). Use native GitHub Assignees for actual ownership. The initial plan leaves work unassigned until a responsible maintainer accepts it; a historical research owner list does not assign new implementation work.

Original code and documentation use the [MIT License](LICENSE), following the research repository. Third-party materials and derived datasets retain their own rights and notices. Report security-sensitive problems through the process in [SECURITY.md](SECURITY.md).
