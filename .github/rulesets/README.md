# Catalog Pipeline ruleset imports

These four UTF-8 JSON files describe the approved repository rules for `Pick-Your-AI/pick-your-ai-catalog-pipeline`. They are configuration inputs, not evidence that GitHub has applied them. No credentials, tokens, account invitations, team IDs or deployment permissions are included.

These files are manually applied repository governance configuration inputs; no workflow automatically applies them.

| File | Ruleset | Target | Bypass actors |
| --- | --- | --- | --- |
| `01-contributor-boundary-default-branch.json` | Contributor boundary: default branch | Default branch | Organization owners; Maintain role 2; Admin role 5 |
| `02-contributor-boundary-branches.json` | Contributor boundary: branches | Other branches, excluding default, contrib and dependabot patterns | Same three actors |
| `03-contributor-boundary-tags.json` | Contributor boundary: tags | All tags | Same three actors |
| `04-review-required-default-branch.json` | Review required: default branch | Default branch | None |

All four specify `enforcement: active`. The first rule restricts default-branch updates. The fourth independently blocks default-branch deletion and force pushes, requires one approval and latest-push approval, and requires `ci-required` from GitHub Actions app `15368`. Its empty bypass list prevents boundary-role exceptions from bypassing review or CI.

## Import through the repository UI

1. Open the target repository's Settings → Rules → Rulesets. Inspect existing rules first; reuse an equivalent existing rule rather than importing a duplicate.
2. Choose New ruleset → Import a ruleset and select one JSON file.
3. Review the imported preview: repository, name, branch/tag target, Active enforcement, ref conditions, rule parameters and explicit bypass actors.
4. Click Create only when the preview preserves the intended settings. Repeat for the remaining missing rules.
5. Collect each newly assigned ruleset ID and its complete API detail. Verify actual enforcement and every control against the approved baseline before reporting success.

The official import operation creates a ruleset after preview; uploading this file is not an update-by-name mechanism. These files are active configurations. Saving them enforces their controls; subsequent source changes must follow the configured pull-request and review requirements. An administrative reauthentication prompt must be satisfied through GitHub's supported flow.

## Import shape and REST distinction

Each file contains one ruleset object. `source_type: Repository` follows GitHub's published UI-import recipe. It identifies the kind of source; the repository selected in the UI supplies the destination.

Generated identities and readback-only metadata are omitted: `id`, `node_id`, `source`, `_links`, `created_at`, `updated_at` and `current_user_can_bypass`. The files contain no repository-wide organization conditions such as `repository_name`; their conditions are `ref_name` only.

For a separately authorized REST create operation, use the documented mutable body fields: `name`, `target`, `enforcement`, `conditions`, `rules` and `bypass_actors`. `source_type` is not a documented REST create body parameter. These UI imports should not be presented as an unmodified REST-response replay.

## Compatibility and readback notes

- `OrganizationAdmin` uses `actor_id: null`, consistent with the audited organization rules. GitHub documents that this ID is ignored for that actor type, which is valid for an organization-owned repository. The numeric repository role IDs are the verified Maintain `2` and Admin `5`, not positions inferred from a role menu.
- The required check binds `integration_id` to the integer `15368`. Do not substitute null, zero, a string or a placeholder. The current REST parameter reference describes an optional integer; this configuration intentionally requires the verified GitHub Actions source.
- Preserve every explicit `bypass_actors` array, including the empty array on the mandatory review/check rule. GitHub's ruleset-history export documentation says historical downloads omit bypass lists. An omitted list is not sufficient evidence of an empty list.
- `require_extra_approval_for_unattributed_changes: true` is preserved from the approved configuration and audited live organization rule responses. The current public REST-create parameter reference does not enumerate that newer field. Its import preservation must be checked in the resulting full detail; it must not be silently dropped or changed to false to make an import pass.
- The update rules omit optional parameters, matching the audited reference. A readback may explicitly report `update_allows_fetch_and_merge: false`; the offline verifier recognizes that equivalent disabled default.
- The four branch exclusions retain both `contrib/**` / `contrib/**/*` and `dependabot/**` / `dependabot/**/*`, with `refs/heads/` prefixes in JSON. The default branch uses `~DEFAULT_BRANCH` and all-ref selections use `~ALL`.
- A missing bypass list or partial API response is an unverified result. Collect a full authorized readback; do not fill omitted fields with assumptions.

Local preparation verifies JSON syntax and exact correspondence with the approved settings. GitHub's current UI parser has not been exercised by this preparation. If it rejects a field, preserve the error and reconcile that specific compatibility issue without relaxing the approved control.

## Primary references

- [GitHub: import a repository ruleset](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository#importing-a-ruleset)
- [GitHub's ruleset recipes and import instructions](https://github.com/github/ruleset-recipes)
- [GitHub's repository import example](https://github.com/github/ruleset-recipes/blob/main/branch-rulesets/PRs%20and%20commits.json)
- [GitHub REST: create a repository ruleset](https://docs.github.com/en/rest/repos/rules#create-a-repository-ruleset)
- [GitHub: ruleset history export](https://docs.github.com/en/enterprise-cloud%40latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository#using-ruleset-history)
- [Organization contribution policy](https://github.com/Pick-Your-AI/.github/blob/main/CONTRIBUTING.md)

The mandatory no-bypass review/check rule is intentionally stronger than the research repository's organization-owner emergency-review exception. The three boundary rules preserve the applicable role pattern without copying unapproved repository-specific team IDs.

