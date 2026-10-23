# Existing issue graph initialization

The optional **Reconcile catalog issue graph** workflow initializes native types and relationships after every canonical issue already exists. It reuses the repository's publication transport, plan validation, pagination, conflict checks and uncertain-write journal. It does not create issues, administer Projects, change repository permissions, edit issue content, assign people, complete work or deploy a service.

The reviewed bootstrap expects **81 issues, 80 internal parent links and 135 blocked-by links**. Program and epic issues use the native `Feature` type; work packages use `Task`. The program's external research [#509](https://github.com/Pick-Your-AI/pick-your-ai-research/issues/509) relationship is a separate authorized cross-repository handoff. The workflow never writes to that repository.

## Inspect the exact input

The default invocation reads local files only and reports the payload's SHA-256:

```bash
python scripts/reconcile_issue_graph.py
```

The payload hash binds the exact reviewed issue definitions. Its source digests must also match the checked-out canonical planning files. An authenticated, read-only inspection can be run locally:

```bash
python scripts/reconcile_issue_graph.py --inspect
```

## Run in GitHub

Use **Actions → Reconcile catalog issue graph → Run workflow** on `main`. Select `inspect` first, enter the exact payload SHA-256, and review the results. Select `apply` in a new manual dispatch only when the input, issue inventory and resulting additions are the authorized scope. The job requires the dispatched commit to remain `main` when application begins.

Only `CompleteDotTech` or `BunsDev` may dispatch or trigger this workflow. Automatic events and ordinary reruns cannot apply changes. The job uses only the repository's ephemeral `GITHUB_TOKEN` with **Contents: read** and **Issues: write**. It requests no organization permission, repository-content write permission, deployment credential or personal token. The two GitHub-owned actions are pinned to the same audited immutable revisions as bootstrap validation.

Stop other issue-graph controllers while applying the plan. Workflow concurrency prevents overlapping runs of this workflow; it cannot lock a person's UI or a separate publisher. Writes are serial and separated by at least two seconds by default. A rate-limit or permission failure stops the queue.

Fresh metadata for the two endpoints of an edge is fetched together through read-only GraphQL. Inverse child lists also use bounded, complete GraphQL connections. The full synthetic rehearsal of inspection followed by all 296 possible mutations uses 816 REST requests including the workflow's main-head check and 751 GraphQL queries. This leaves room within the normal repository token limits, but other workflow activity shares the quota; rate-limit failures still stop the run. Unrelated issue inventory pagination can add requests.

## Preservation and verification

Before any mutation, the initializer resolves stable markers through a complete all-state issue inventory and verifies the repository's numeric identity. Missing or duplicate issues, foreign identities, conflicting native types, unexpected parents, extra blockers and unexpected children stop application.

Existing matching types and edges are preserved. New metadata is added only while affected issues still match their original body, title, labels, open/unassigned state and empty discussion/milestone state. Every write gets a fresh identity/relationship check and a separate readback. It never force-reparents, removes links, edits a checklist, resets state, or changes an assignee. GitHub does not provide a transaction across this whole graph: a stopped run can have a verified partial result, which must be reported accurately.

GitHub's type-update endpoint also provides no transaction linking the preceding read to the later type change. An edit by another controller in that small interval remains a concurrency limitation; stop other controllers during initialization and review the final receipt.

An issue type can be silently ignored by the issue API without sufficient access. A successful HTTP response therefore does not establish success; the initializer requires the actual `Feature` or `Task` value in a fresh issue readback. If the repository token cannot persist native types, an authorized maintainer can initialize them through GitHub's UI and rerun after reconciling the saved receipt.

The final result verifies both child-to-parent links and the inverse child lists, all prerequisites, all types and exact issue identities. It remains `complete_mission: false`: Project fields/views, governance, code delivery, implementation acceptance and production operation are separate outcomes.

## Interrupted or uncertain writes

The journal is flushed before every request. A missing readback or uncertain network outcome leaves an intent record and stops further work. Reusing that journal refuses to retry an absent uncertain operation; an observed successful operation can be recovered by identity.

The runner's `.state/issue-graph/` is temporary. The workflow prints the sanitized public journal and readback in its persistent logs and step summary, including a single `RESUME_JOURNAL_JSON=` line. After an interrupted or uncertain run, inspect live state, preserve that receipt, and put its exact JSON value in the next dispatch's optional `resume_journal` input. The restored journal must match the same repository, input fingerprint and permitted operation keys. Do not omit or alter an unresolved receipt simply to force a retry. If cancellation prevented a final receipt from being printed, reconcile the affected live graph before any new dispatch; no automatic retry is authorized by a missing log.

## API references

The implementation uses GitHub's documented [issue update](https://docs.github.com/en/rest/issues/issues#update-an-issue), [native sub-issue](https://docs.github.com/en/rest/issues/sub-issues#add-sub-issue), and [issue dependency](https://docs.github.com/en/rest/issues/issue-dependencies#add-an-issue-dependency) operations. The [GraphQL Issue schema](https://docs.github.com/en/graphql/reference/issues#issue) defines the fresh metadata and child connections. The [GITHUB_TOKEN tutorial](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token) describes the repository-scoped workflow token; the [REST rate-limit documentation](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) defines its request allowance, and the [REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api) describe serial requests and mutative-request throttling. References were checked on 2026-10-23; the inherited transport pins API version `2026-03-10`.
