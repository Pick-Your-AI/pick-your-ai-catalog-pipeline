# GitHub repository and Project setup

## Publication status

This document separates the configuration specification from dated execution evidence. At **2026-10-23 04:54:13 UTC**, the public repository [Pick-Your-AI/pick-your-ai-catalog-pipeline](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline) has verified ID `1430404474` and default branch `main`. The latest source-publication receipt verifies revision [`63c1c6e881ddaba817fb1c58a6a8e629ad85e33f`](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/commit/63c1c6e881ddaba817fb1c58a6a8e629ad85e33f) and [hosted `ci-required` success with 100 tests](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/actions/runs/39900854598). The actual organization Project is [**Pick Your AI — Catalog Pipeline, #8**](https://github.com/orgs/Pick-Your-AI/projects/8); its number was observed after creation.

All 81 issues have audited identities, exact planned titles/bodies/checklists, open state and unassigned ownership. Project #8 is public with the exact requested title and description, all 11 field definitions and option sets, ordered Status options, and 81 members. Five automatic review/status workflows are disabled; automatic addition of sub-issues is enabled. These Project observations were read back by the executor through GitHub's UI. Project field-value initialization and all eight saved views remain incomplete and require a full final readback; membership does not certify field values.

The manual graph [inspection run](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/actions/runs/39900973114) succeeded. The [apply run](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/actions/runs/39901223975) completed successfully at 04:51:23 UTC. Its final `applied-and-read-back` receipt verifies 81 native types, 80 internal parent links and 135 blocked-by links, with 296 verified journal operations and no pending or rejected operations. Four independent representative relationship reads also passed. The research #509 parent remains a separate pending cross-repository handoff. Team grants are blocked by GitHub's administrative reauthentication (sudo) prompt. Branch/tag rules and required-check enforcement are not configured or verified; the 04:32:54 UTC source readback still showed `main` unprotected. Keep `complete_mission: false`; see [BOOTSTRAP_STATUS.md](BOOTSTRAP_STATUS.md) and [execution-receipt.json](../planning/execution-receipt.json).

The published foundation is the authorized initial seed. Subsequent substantive changes follow the organization review and branch policy; an initially unprotected branch does not create a continuing review exemption. Refresh live state before each remaining mutation and preserve the existing repository, Project, issue identities and human progress.

| Resource | Required configuration |
|---|---|
| Organization | `Pick-Your-AI` |
| Repository | [`pick-your-ai-catalog-pipeline`](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline); verified ID `1430404474` |
| Repository visibility | Public, verified at creation |
| Default branch | `main`; latest source revision in this snapshot `63c1c6e881ddaba817fb1c58a6a8e629ad85e33f` |
| Organization Project | [**Pick Your AI — Catalog Pipeline, #8**](https://github.com/orgs/Pick-Your-AI/projects/8), verified after creation |
| Project description | Organization-wide AI research ingestion, source governance, normalization, evidence review, catalog publishing, freshness, and consumer delivery. |
| Project visibility | Public, verified through GitHub UI; exclude private source and operating details |
| Parent research authority | [pick-your-ai-research #509](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509) |
| Source of planned scope | [planning/project-backlog.json](../planning/project-backlog.json) |
| Source of live execution state | Actual GitHub issues, Assignees, native hierarchy, dependencies and Project items |

Recommended repository topics are `ai`, `research`, `data-pipeline`, `data-catalog`, `data-provenance`, `etl`, `evidence`, `open-source` and `pick-your-ai`. The description must identify a planning/implementation repository and must not claim an already deployed service. Disable any unintended deployment workflow; the bootstrap CI only validates repository artifacts.

## Inspect and reconcile before mutation

Read the current [organization contribution policy](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md), repository permissions, target-repository existence, all matching open and closed Projects, all-state target issues, relevant PRs, field definitions, views, native parents and blockers. Exhaust pagination and record the observation time. Search by canonical repository identity, Project title, stable plan marker and outcome, not title text alone.

The historical inspection found established Projects #1–#7. Their IDs, options and visibility snapshots are evidence of conventions only. They do not establish the next available identity or certify today's settings. In particular, old Project #2 documentation initially described a private Project and later recorded public visibility. Current authenticated readback takes precedence.

Preserve completed research, existing implementation issues, assignees, comments, checklists, Project values and accepted handoffs. A published baseline must not reset live status to Backlog. Resolve any identity collision or competing implementation before creating another issue. An uncertain write response requires reconciliation by stable identity before retrying.

## Native hierarchy and issue semantics

The baseline contains **81 intended issues: one Program, 16 Epics and 64 Work Packages**. Every epic has four independently reviewable packages. Implementation and validation steps are task checklists within their owning package. Promote a checklist task to a native Task issue only when it gains a distinct owner, review boundary or deliverable; preserve its stable ID and link the replacement so it is not counted twice.

The planned target-repository hierarchy has **80 internal parent edges**: 16 Epic → Program and 64 Work Package → Epic. The program also references research #509 as its canonical research handoff. Reconcile its proposed native cross-repository parent under #509 against the live hierarchy before attaching it, and record that external edge separately. Preserve #509's own parent, existing children, scope and status. Never force a reparent operation to make a manifest appear consistent.

Program and Epic issues use the existing organization **Feature** issue type where it is enabled; Work Packages and promoted Tasks use **Task**. The Project's **Record Type** field distinguishes Program, Epic, Work Package and Task without pretending native GitHub issue types are hierarchical levels.

Each issue body contains its stable plan marker, outcome, scope, deliverables, task checklist, acceptance criteria, required evidence, dependencies and contextual references. Proposed owner roles describe expertise; only native GitHub Assignees establish actual ownership. The initial backlog does not assign absent people, estimates, deadlines or operating commitments.

Use native blocked-by relationships for genuine prerequisite outputs. A related research result, consumer reference, compatibility relationship or optional future integration is not automatically a blocking dependency. The directed prerequisite graph must be acyclic. Unknown prerequisite completion remains unverified; a baseline does not turn it into a completed gate.

## Project fields

Configure the following fields on the dedicated organization Project. Reuse its native Status and Assignees. Do not create an Owner field or encode status, priority or ownership again as labels. The versioned backlog is the canonical source of the selected option spellings; obtain new field and option IDs from actual readback.

| Field | Type | Required options or interpretation |
|---|---|---|
| Status | Native single select | Backlog; Ready; In Progress; In Review; Blocked; Done |
| Priority | Single select | P0; P1; P2; P3 |
| Workstream | Single select | Program, plus the 16 exact epic workstream names in the baseline |
| Record Type | Single select | Program; Epic; Work Package; Task |
| Readiness | Single select | Ready; Needs Input; Blocked; Awaiting Decision |
| Evidence Confidence | Single select | Unverified; Low; Medium; High; Not Applicable |
| Source Rights Status | Single select | Not Assessed; Research Only; Conditional; Approved; Restricted; Revoked; Not Applicable |
| Dependency Status | Single select | Not Assessed; No Dependencies; Waiting; Ready; Blocked |
| Effort | Single select | Unknown; S; M; L |
| Release Phase | Single select | Bootstrap; Foundation; Bounded Pilot; Beta; Production; Expansion |
| Acceptance Status | Single select | Not Started; In Review; Accepted; Changes Required; Deferred |
| Assignees | Native | Only actual accepted owners; blank until accepted |

Evidence Confidence assesses the particular work item's supporting evidence, not whether its topic sounds plausible. It does not replace claim-level verification in catalog data. Source Rights Status summarizes the scoped work and does not grant blanket rights to a provider. Conditional records name the missing conditions; Not Applicable is used only where the issue has no source-use decision. Effort remains Unknown without a defensible estimate.

Readiness follows the exact four requested values. Use Needs Input with an explicit missing-owner reason while an issue has no accepted Assignee; do not invent a fifth owner field. Ready requires an accepted owner, scoped deliverables and usable prerequisite outputs. Awaiting Decision names the decision and accountable authority. Blocked identifies an actual impediment and next action. Status and Readiness are distinct: a planned package can remain Backlog while a decision is awaited.

Acceptance Status is separate from ordinary activity. Accepted requires exact-artifact review against all owning criteria. Repository creation does not accept future ingestion, evidence, consumer or operational work. Deferred requires an explicit reviewed scope decision and reason; it is not a convenient substitute for unfinished work.

Initial values are taken from each record's canonical baseline. Preserve existing live values during reconciliation. Initialize a new Project item only when its issue was demonstrably created by this publication and remains unchanged, open and unassigned. A pre-existing issue newly added to the Project requires explicit field reconciliation; adding membership does not authorize resetting its progress. Read each initialized value back after mutation. Do not configure automatic issue-close-to-Accepted behavior.

## Saved views

The user request ended after “Currently.” The additional views below complete the requested navigation using the organization's existing readiness, evidence, dependency and release conventions. They are proposed saved configurations, not created views or assumed view numbers.

| View | Layout and filter | Grouping and visible focus |
|---|---|---|
| Program Overview | Table; `record-type:Program,Epic` | Workstream; Title, Status, Priority, Assignees, Parent issue, Sub-issues progress, Acceptance Status |
| Epics and Work Packages | Table; `record-type:Epic,"Work Package",Task` | Hierarchy enabled; Workstream, Parent issue, Sub-issues progress, Status, Priority, Readiness |
| Priority and Readiness | Table; `-status:Done` | Group by Priority; show Readiness, Assignees, Dependency Status, Effort and Release Phase |
| Currently Active | Board; `status:"In Progress","In Review"` | Status columns; Workstream swimlanes, Assignees, Priority and Acceptance Status |
| Blocked and Decisions | Table; `readiness:Blocked,"Awaiting Decision","Needs Input"` | Readiness; show prerequisite links, Dependency Status, Assignees and decision references |
| Rights and Evidence | Table; `-status:Done` | Source Rights Status; show Evidence Confidence, Readiness, Workstream and Acceptance Status |
| Consumer Handoffs | Table; scoped to the baseline's consumer-integration workstream | Workstream; show Assignees, Dependency Status, Release Phase and Acceptance Status |
| Release Readiness | Table; `-acceptance-status:Accepted,Deferred` | Release Phase; show Priority, Status, Readiness and Acceptance Status |

Use the actual configured field names when GitHub derives filter identifiers, and test each saved filter by reading its resulting item membership. Workstream values for Consumer Handoffs must be resolved from the created field's actual options rather than a guessed identifier. Sort priority views by Priority and stable title; no invented date range or iteration is needed.

The saved filters listed here use values within a single field or a simple exclusion; they do not require cross-field OR expressions. A separate metadata audit detects missing owners or fields and verifies each view's actual result set. An empty Currently Active view is expected for a newly published backlog and must not be populated by inventing progress.

Save every view, reload it and inspect its title, layout, filter, grouping, sorting, visible fields and expected membership. Record actual view numbers and URLs only after readback. View names in documentation alone do not satisfy the request to configure a Project.

## Labels, ownership and branch rules

Reuse selective kind/topic labels from the organization, such as documentation, enhancement, question and security, adding narrowly useful pipeline topics only where necessary. Do not duplicate Priority, Status, Readiness or owners in labels. Prefer issue types and the Record Type field for hierarchy. Record each actual label's name and description after creation.

The canonical organization policy grants access through teams. Parent Maintainers, Research, Websites and Mobile Devices teams have triage roles; repository child teams provide write access; the designated lead-maintainer teams provide administration. Team display names do not establish slugs or grants to this new repository. The bootstrap must not invent team identifiers, add unapproved members or claim that CODEOWNERS grants access. Configure repository grants only for verified, authorized teams; otherwise keep an explicit pending governance item.

Follow the organization's separate contributor boundaries for main, non-contributor branches and tags. Early contributors use `contrib/<login>/<topic>`; maintainers own other branches. Require a PR, one approval from someone other than its author and approval of the latest push by someone other than the last pusher. Preserve the prohibition on deletion and force-push of main. Required checks must match the actual workflow job names after their first successful run. Administrative bypass is not ordinary bootstrap completion.

Use only GitHub-owned `actions/*` actions, pinned to immutable verified commits, with the minimal permissions needed by the validation workflow. Public PR checks require no source, publication or deployment credentials. A protection readback is distinct from a written policy: document an unapplied ruleset as unapplied.

## Safe publication order

1. Discover and reconcile the target repository, equivalent Projects and existing backlog records. Retain the inventory and actual IDs.
2. Create or reuse the public repository, initialize main, set metadata and publish the reviewed bootstrap without claiming runtime delivery.
3. Apply verified team access and repository rules through the supported administrative interface. Record any unavailable controls explicitly.
4. Create or reuse the organization Project, set its name, description, README, visibility and repository link, and read back its actual identity.
5. Create or reconcile field definitions and store their actual IDs and option IDs.
6. Create or reconcile the 81 planned issues by stable markers. Persist each successful identity before continuing; do not blindly retry an uncertain request.
7. Reconcile native parent edges and genuine blocked-by edges. Stop on conflicting existing ancestry rather than replacing it.
8. Add each issue once to the Project, initialize fields only for this publication's unchanged new issues/items, and preserve live execution state.
9. Configure and save the views, then validate their reloaded configuration and complete matching memberships.
10. Read back repository metadata, all issues, native relationships, Project membership/fields/views, rules and CI. Save an attributable publication report distinguishing passed, failed, blocked and unverified checks.

An access blocker does not authorize exporting credentials, inventing authenticated sessions, weakening organization rules or marking resources as created. Keep the complete prepared baseline available and report precisely which supported administrative capability is missing.

## Prepared publisher helper

[`scripts/publish_plan.py`](../scripts/publish_plan.py) uses Python's standard library and the already authenticated GitHub CLI. It is restricted to this organization, repository and Project identity. The preparation environment did not have an authenticated `gh` administration route; the live modes have therefore **not been executed**. Offline tests exercise a stateful synthetic GitHub adapter and are not hosted acceptance evidence.

The default command validates the real prepared payload and configuration without constructing a network adapter, launching a subprocess or writing to GitHub:

```sh
python scripts/publish_plan.py
```

In a separately authorized environment with `gh` installed and already authenticated, inspect the live organization and repository first:

```sh
python scripts/publish_plan.py --inspect
```

`--inspect` reads all pages of repositories, Projects, issues, field definitions, membership and native relationships. It performs no mutations. Partial GraphQL responses, duplicate stable identities, conflicting parents, unexpected blockers and incomplete pagination stop reconciliation. The configured GitHub account must have visibility into all relevant resources. Write mode requires active organization-owner membership to avoid relying on a partial administrative inventory; the helper does not acquire credentials or log in.

The explicit write mode creates missing resources and reconciles their confirmed identities:

```sh
python scripts/publish_plan.py --apply
```

The helper can create the public repository, create or reuse the dedicated Project, initialize a newly created Project's public visibility and description, link it to the repository, add missing single-select fields and topic labels, create missing marked issues, attach native parent and blocked-by relationships, and initialize eligible new Project items. GitHub supplies the actual Project number. It creates no issue comments, mentions, Assignees or invitations.

A new repository is created with GitHub's `auto_init` option, which adds GitHub's initial content. Its default branch must read back as `main`; otherwise publication stops with a pending repository configuration step. The helper **does not upload or commit this bootstrap**, create or merge a content PR, configure saved views or README, set repository topics, grant team permissions, establish CODEOWNERS, change branch rules, configure required checks or deploy a service. Submit the prepared files through a reviewed branch and independent approval, and finish those administrative controls through supported interfaces.

Existing issue bodies, titles, types, labels, assignments and execution state are preserved. Existing Project options and values are preserved. The only option replacement is initial Status setup on a demonstrably helper-created, empty Project. A differently named equivalent Project, multiple candidates, private pre-existing Project, conflicting existing field or archived target item requires explicit reconciliation. A failed or uncertain read is never treated as proof that a resource is missing.

Write intent and confirmed identities are saved atomically under the ignored `.state/publication/` directory. Keep these receipts across resumptions. A timeout or unknown outcome leaves an uncertain receipt: the next run may reconcile a visible matching resource, but will not blindly repeat the write or claim that it created the recovered resource. Do not delete receipts or stale locks to make an error disappear. Confirm the prior process is stopped and resolve the identified uncertainty. A changed payload/configuration fingerprint also requires deliberate reconciliation.

An eligible issue is reread before each initial field write. If its body, title, type, labels, state or assignment changes, the helper stops or preserves it rather than continuing to apply baseline activity values. GitHub does not provide a transaction spanning issue content and Project field writes, so a very short concurrent-edit race remains; schedule initialization without simultaneous edits and inspect the final receipt.

The final local `readback.json` reports actual resource IDs and URLs, native relationship counts, Project membership, preserved live fields, issue content hashes and differences, and Project metadata differences. It always reports `complete_mission: false` until the separate content, governance, UI-view and hosted-check acceptance steps are completed. Successful helper execution alone is not complete repository initialization or production delivery.

Use `--write-delay SECONDS` to pace writes within the authenticated account's limits. Rate-limit or access rejections stop execution; the helper does not bypass limits or automatically retry unknown outcomes. `--state-dir PATH` changes the local receipt location. `--payload PATH` and `--config PATH` support a reviewed file location while retaining fixed organization/repository scope and structural validation.

Run the offline safety suite with:

```sh
python -m unittest discover -s tests -p test_publish_plan.py -v
```

The release phases are **Bootstrap, Foundation, Bounded Pilot, Beta, Production and Expansion**, in that order. The helper rejects dependency cycles, ancestor prerequisites that deadlock parent completion and prerequisites scheduled in a later phase.

## Verification checklist

- Repository identity, public visibility and default branch match the intended target.
- Every required foundational file is present at the verified main revision.
- The complete issue inventory has one unique stable marker per planned issue and no duplicate outcome.
- All 81 planned issues have actual repository and immutable issue IDs; no draft Project item stands in for a requested issue.
- All 80 internal native parent edges match the baseline; any external parent edge is recorded independently.
- Every native blocker is a genuine prerequisite; there are no missing/extra edges or dependency cycles.
- Project membership contains each planned issue once; field values match actual option IDs and preserve prior progress.
- Native Assignees represent accepted owners, with no invented Owner field or implicit assignments.
- Saved views survive reload and their membership follows their filters, including deliberately empty views.
- CI runs against the exact delivered revision and passes the documented structural, schema, test and generated-document checks.
- Applied rulesets and required checks are verified independently of their written configuration plan.
- The final report explicitly distinguishes repository/backlog initialization from production platform implementation and deployment.

## Inspected precedents

- [Organization access, branch and review rules](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md)
- [Leaderboard structured planning conventions](https://github.com/Pick-Your-AI/pick-your-ai-leaderboard/blob/main/planning/README.md)
- [Leaderboard delivery plan](https://github.com/Pick-Your-AI/pick-your-ai-leaderboard/blob/main/docs/DELIVERY_PLAN.md)
- [Historical Projects #1–#6 inventory](https://github.com/Pick-Your-AI/pick-your-ai-leaderboard/blob/main/planning/organization-inventory-2026-10-18.json)
- [Historical Project #6 fields and views](https://github.com/Pick-Your-AI/pick-your-ai-leaderboard/blob/main/planning/project-configuration-readback-2026-10-18.json)
- [Market Project #2 configuration and later visibility readback](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/market-research/project-configuration.md)
- [Mobile Projects #4 and #5 field snapshots](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/prompts/mobile/project-fields.json)
- [Sustainability Project #7 configuration](https://github.com/Pick-Your-AI/pick-your-ai-sustainability/blob/main/docs/project-configuration.md)
- [Sustainability setup acceptance and its limits](https://github.com/Pick-Your-AI/pick-your-ai-sustainability/blob/main/docs/program-setup-acceptance.md)
