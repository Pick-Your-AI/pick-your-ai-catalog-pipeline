# Contributing

This repository follows the [Pick Your AI organization contribution policy](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md). That policy owns access, branch restrictions, approval and merge rules; this document adds pipeline-specific planning, evidence and validation requirements.

## Choose bounded work

Start from an existing backlog record or issue. Read the objective, artifact paths, acceptance criteria, dependencies and linked research decisions. Check for an existing issue, branch or PR before creating another. Preserve stable planning IDs and reference the canonical issue.

Work that changes shared contracts, source-use policy, evidence semantics, publication eligibility or a consuming client's behavior needs the relevant producer and consumer review. A small documentation correction does not require a new program or a duplicate research issue.

Use native subissues for deliverables that can be reviewed or owned independently. Keep small implementation steps as checklists. Parent-child structure expresses decomposition; blocked-by expresses a genuine prerequisite. Informational handoffs belong in the issue description and dependency documentation.

## Ownership and access

Use native GitHub Assignees when a person accepts responsibility. Do not assign new pipeline work based solely on an old research owner table. Unclaimed work remains unassigned. The machine plan may describe a responsible role without implying that a named person has accepted it.

Repository access is granted through the organization's teams. Only authorized organization administrators configure access, and only CompleteDotTech and BunsDev change team membership under the current organization policy. A CODEOWNERS entry does not grant repository permissions or establish a person's acceptance of an issue.

The bootstrap does not claim that teams, repository rules, private reporting, Project permissions or branch checks are configured until those settings are read back from GitHub. See [Project setup](docs/PROJECT_SETUP.md).

## Branches and pull requests

When the repository is available, clone it or use a fork. Early contributors with authorized access use `contrib/<login>/<topic>` branches under the organization policy. Maintain separate branches or worktrees for parallel work, and avoid editing another contributor's branch.

A pull request should explain the problem, the resulting behavior, the relevant plan/issue IDs, evidence and contract implications, actual verification results, and any remaining acceptance criteria. Link exact upstream artifacts and revisions when the change depends on research or shared contracts.

Every PR into `main` requires the independent approval and latest-push approval specified by organization policy, together with the checks actually configured on the repository. Do not bypass required approval or claim that the author approved their own work. Initial creation of an empty repository is a bootstrap operation, not evidence that later changes are exempt from review. Any exception must have explicit applicable authority and an accurate audit trail.

Use `Refs #123` for a partial delivery. Use a closing directive only when the merge will satisfy every acceptance criterion and required receiving handoff. Check the PR body, commit messages and manually linked issues before merging; prose that negates a closing keyword does not reliably prevent GitHub from closing an issue.

## Research and contract changes

Research methods and accepted decisions remain in [pick-your-ai-research](https://github.com/Pick-Your-AI/pick-your-ai-research). Read its [research method](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/RESEARCH_METHOD.md), [submission workflow](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/RESEARCH_WORKFLOW.md) and [shared execution rules](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/prompts/SHARED.md).

The frozen builder v1 import must remain unchanged. New catalog entities, record history, rights envelopes and publication manifests belong to separately versioned pipeline contracts. A builder projection must identify its accepted contract version, input revisions, transformations, unsupported semantics and migration behavior. New builder fields or kinds require the existing cross-owner contract process.

Do not label an illustrative compatibility rule as an approved universal fact. Do not relabel a source-checked statement as an independently reproduced measurement. Keep prices, scope conditions, quotes and estimates distinct.

## Source material and synthetic examples

The [publication eligibility handoff](https://github.com/Pick-Your-AI/pick-your-ai-research/blob/main/docs/PUBLICATION_ELIGIBILITY_HANDOFF.md) is mandatory context for any real-data change. The MIT license on this repository does not clear upstream source content. A field's retrieval, internal use, public display and redistribution permissions require their own evidence and conditions.

All bootstrap examples are synthetic. Keep their synthetic markers and reserved identities visible, including in examples of rights decisions, review receipts and releases. A test fixture must never be used as a production permission or accepted research claim.

Keep secrets, personal/customer information, restricted source content, raw crawls, large datasets and model weights out of public Git. Sanitize external-artifact manifests and retain stable references without credentials or temporary signed access tokens. Report vulnerabilities privately using [SECURITY.md](SECURITY.md).

## Local validation

Use Python 3.12 from the repository root:

```bash
python -m pip install -r requirements-validation.txt
python scripts/validate_plan.py
python scripts/validate_examples.py
python scripts/render_docs.py --check
python -m unittest discover -s tests -v
```

If the plan changes, regenerate documents with `python scripts/render_docs.py`, inspect the resulting diff, then rerun the checks. Report what passed, what failed and what was not run. Do not describe an offline consistency check as verification of live source terms, external hashes, deployed behavior or GitHub configuration.

Changes to validators need meaningful positive and negative tests. Relevant cases include duplicate identities, hierarchy/dependency cycles, missing references, unreviewed publication, mixed-source rights, revision mismatch, corrupt artifacts and synthetic-to-real promotion. Keep workflow permissions minimal and use only approved `actions/*` actions, pinned to immutable revisions.

## Completion

A merged partial PR may be useful while its issue stays open. Done requires the full artifact, passing applicable checks, required reviews, complete acceptance criteria and any required consumer receipt. A parent additionally requires accepted child outcomes and its own acceptance. Update live issue/Project state only after verifying the exact merged result. Repository setup and issue creation do not complete the planned production platform.

## Routing decisions

For an unresolved decision, first read the existing issue, its assignees, relevant
decision record and related pull requests. Preserve accepted ownership and local
review, evidence, security and release requirements. Routing identifies a contact;
it does not grant access, appoint an owner, authorize publication or waive a gate.

Use the canonical [escalation guide](https://github.com/Pick-Your-AI/.github/blob/main/docs/governance/ESCALATION.md) and
[versioned routing policy](https://github.com/Pick-Your-AI/.github/blob/main/governance/escalation-policy.json). These links depend on the organization
governance change merging; until then, use its reviewed checkout and describe the
route as provisional. Do not claim the central tooling is installed or active.

The order is repository team → repository maintainer → repository lead maintainer
→ applicable parent teams → CompleteDotTech. Record a disposition at each level,
including unresolved, vacant, pending-acceptance or inaccessible roles; membership,
team-management status and repository permissions do not establish accepted
operational ownership. Keep owner placeholders for the final fallback. Do not
silently skip an unresolved role or treat a proposed mapping as accepted.

An operator with read access must refresh the private snapshot before resolving:

```sh
python /path/to/org-checkout/governance/router.py refresh --policy /path/to/org-checkout/governance/escalation-policy.json --snapshot /private/path/routing-snapshot.json --status /private/path/routing-status.json
python /path/to/org-checkout/governance/router.py resolve --policy /path/to/org-checkout/governance/escalation-policy.json --snapshot /private/path/routing-snapshot.json --repo Pick-Your-AI/pick-your-ai-catalog-pipeline --max-age-seconds 86400 --status /private/path/routing-status.json
```

Here `86400` is an **operator-selected example**, not an approved default. Select
an appropriate explicit maximum age; a proposed policy value does not supply one.
Check that refresh succeeded. If refresh fails, stop recipient selection and
report the failure; the last successful snapshot is retained for diagnosis, not
as a current route. Report stale or incomplete coverage explicitly. Keep snapshots,
raw API responses, rosters and private
identities outside public Git and public issues. Share only the necessary public
team destination and a sanitized decision summary.

When escalation is needed, include the decision needed, current responsible role,
prior disposition and proposed next recipient. Reuse information already in the
issue or PR; routine contributions need no full escalation history. Send nothing
and change no assignment automatically. Sensitive reports follow the existing
private security/support process.

The owner-selected scope of [organization issue #14](https://github.com/Pick-Your-AI/.github/issues/14)
is all changes in Research, Sustainability, Applications, Papers, Catalog Pipeline
and Datasets. This records scope only: current independent-review and branch/check
requirements remain in force. Any proposed enforcement change requires separate
approval; no review exception or CODEOWNERS change is established here.
