# Governance

## Policy inheritance

The [organization contribution policy](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md) controls access, branches, reviews, merges and approved Actions. Research's [shared execution rules](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/prompts/SHARED.md), [research method](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/RESEARCH_METHOD.md), [contract adoption](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/contracts/v1/ADOPTION.md) and [publication handoff](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/PUBLICATION_ELIGIBILITY_HANDOFF.md) remain authoritative for their respective research and source-use boundaries.

This repository implements those accepted decisions. A pipeline implementation cannot silently reinterpret a research grade, broaden a source permission, change a frozen builder contract, or substitute for a consuming owner's acceptance.

## Bootstrap state

As of **2026-10-23 00:24:35 UTC**, the [public repository](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline) (ID `1430404474`) and [organization Project #8](https://github.com/orgs/Pick-Your-AI/projects/8) have verified identities, and issue publication is in progress. The remote main branch has the verified initial commit `b30a2eabbd40404d71088c927e9b95ec0df50d1b`. Foundation upload, complete issue inventory and native relationships, Project settings, team grants, branch protection, required checks, private reporting and hosted CI are not established by creation alone. Initial readback found no rulesets and an unprotected main branch; the authorized foundation seed remains distinct from subsequent review-governed changes. [Project setup](PROJECT_SETUP.md) records the dated execution state and remaining acceptance steps.

Creating an empty public repository and seeding its foundation is a bootstrap operation. It does not waive review on subsequent substantive changes. Existing repository rules must not be weakened to import the foundation. An independent assistant analysis is useful evidence but is not another eligible person's GitHub approving review.

## Responsibility

| Role | Responsibility | Boundary |
| --- | --- | --- |
| Organization administrator | Repository/Project creation, authorized team grants and administrative settings | Team membership changes follow the organization's named-admin policy |
| Pipeline maintainer | Implementation plan, code review routing, integration and release coordination | Does not independently grant source-use rights or revise research conclusions |
| Research/domain owner | Exact source findings, claim interpretation, domain scope and reviewed handoffs | Does not automatically own or approve runtime implementation |
| Source-rights decision maker | Exact material/use/product decision, conditions, evidence and changes | Missing or ambiguous decisions cannot be converted to permission |
| Contract reviewer | Versioning, consumer compatibility, migrations and shared semantics | Frozen builder v1 remains unchanged |
| Contributor | Accepted bounded deliverable and evidence | An issue or role description does not grant access |
| Receiving consumer | Tests and accepts an exact release/projection for its intended use | One client's receipt does not accept another client or a broader use |
| Release/operator role | Executes authorized promotion, rollback and operational response | Production credentials and deployment authority require separate acceptance |

Role descriptions are responsibilities, not appointments. Use native GitHub Assignees for actual accepted personal ownership. Leave unclaimed implementation records unassigned. Do not create a duplicate owner Project field or copy names from old research tables into every issue.

Repository permissions are team-based. Verify the applicable existing team or authorized new team before granting access or adding team CODEOWNERS. A CODEOWNERS file supplies review routing only; it does not create permissions or establish task acceptance.

## Sources of truth

| Information | Authority |
| --- | --- |
| Accepted research policy and evidence | Exact upstream research artifact and linked decision/review |
| Builder v1 shape | Frozen research `contracts/v1/`, with its documented provenance |
| Pipeline contract | Separately versioned schema and accepted migration/consumer decision |
| Local scope and hierarchy | `planning/project-backlog.json` |
| Local decision status | `planning/decision-register.json`, with real decision evidence |
| Intended release and synthetic boundary | `planning/release-manifest.json` |
| Domain coverage and known gaps | `planning/coverage-matrix.json` |
| Current issue owner/state and native relationships | Fresh GitHub readback |
| Project identity, fields, options and views | Fresh GitHub readback |
| Deployed artifact and acceptance | Exact release identity, deployment evidence and consumer receipts |

Generated documents explain the machine-readable sources. They must not become independent editable copies of the same hierarchy. When GitHub and a local snapshot disagree, refresh evidence and reconcile deliberately; do not silently overwrite newer work.

## Decisions and review

Record material decisions with context, alternatives, rationale, affected artifacts and consumers, consequences, responsible decision role, status and evidence. Distinguish proposed architecture choices from accepted source policy and actual operational authorization.

Review depth follows impact. Contract, rights, provenance, identity, security and publication changes require review of positive and rejection behavior, migration/replay consequences, affected consumers and failure handling. Ordinary implementation still requires the organization's independent approving review and approval of the most recent push.

Do not mark a decision accepted based on a placeholder reviewer, an inaccessible source, a synthetic receipt, a test result or an author's assertion. A pending decision can block a particular release or work package while independent design and testing continue.

## Hierarchy and dependencies

Use Program → Epic → Work Package → Task to distinguish delivery scope. A small step can be a checklist inside the task; create another native subissue only when it has a separately reviewable result. Every native child has a clear canonical parent.

A blocking dependency must name the required artifact or decision and explain why meaningful acceptance cannot proceed without it. Informational coordination and compatibility relationships are not automatically blockers. Keep the hierarchy and dependency graph independently acyclic, and do not create cycles to represent mutual review.

The accepted outputs of research #39/#40/#41/#60 are references. Their closed status at bootstrap does not justify creating replacement research issues or treating them as unresolved blockers. New changes to their accepted scope require a specific new proposal and affected-owner review.

## Evidence, rights and confidence

Assess claims separately from records and sources. Preserve the distinction between primary documentation, vendor claims, independent measurements and estimates. Confidence is a separate assessment with basis and limitations. A source-checked fact is not automatically independently verified.

Rights decisions identify source, material, intended use, product scope, applicable fields, governing evidence, date, conditions and change triggers. Unknown, denied, conditional and permitted are distinct states. A permissive record fragment does not clear a mixed-source record. Catalog publication and downloadable/API redistribution need separate consideration where their uses differ.

Refresh schedules serve operations. They do not introduce an unapproved expiry rule for version-pinned facts or imply that an old current-state observation remains current. Preserve immutable history and current-state as-of disclosures.

## Acceptance and completion

Local validation, peer review, receiving acceptance and deployment evidence answer different questions. Record all that apply; do not substitute one for another.

A task is Done only when its deliverable exists at the exact accepted revision, acceptance criteria and relevant checks pass, independent review is recorded, and required receiving handoffs are accepted. A parent also needs its children and its own integration criteria. An issue can remain open after a useful partial PR merges.

Bootstrap acceptance covers the foundation and its verified setup. Runtime backlog work remains Backlog, Ready, Blocked or another accurate state until implemented. Creating many issues or a Project does not complete those deliverables. Use `Refs` for partial work and inspect closing directives immediately before merge.

## Change control and escalation

Preserve history for corrections, superseded decisions and duplicates. Link the canonical issue and explain a duplicate before closure; do not delete unique information. Refresh existing work before reruns so that repository and Project setup is idempotent.

When permissions, a required independent review, a specific source decision or a consumer receipt are unavailable, complete independent authorized work and record the exact missing prerequisite. Do not invent acceptance, bypass access controls, or broaden another person's authority to make the plan appear complete.
