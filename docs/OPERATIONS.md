# Operations plan

## Current operating state

This is an operational design for the planned pipeline. The bootstrap has no deployed service, scheduled connector, live release endpoint, production credentials, on-call rotation, paid source account or approved production SLO. The release manifest must preserve its actual bootstrap/synthetic state. GitHub setup and local checks are tracked separately in [Project setup](PROJECT_SETUP.md).

The local verification entry points are:

```bash
python scripts/validate_plan.py
python scripts/render_docs.py --check
python -m unittest discover -s tests -v
```

These commands validate the repository foundation. They are not production collection, release or recovery commands. Operational scripts and infrastructure require their own implementation, review and tested runbooks before use.

## Required control points

| Stage | Required control | Failure behavior |
| --- | --- | --- |
| Source registration | Exact material/use/product decision, source identity, access method, conditions and responsible decision role | Unapproved operations remain disabled |
| Acquisition | Allowlisted scope, credential isolation, bounded requests, rate budgets, checkpoints and source-policy enforcement | Stop or back off; retain a sanitized failure receipt; do not broaden scope |
| Parsing | Untrusted-content isolation, payload/resource limits, typed parsing and provenance retention | Quarantine malformed or unsafe input; do not publish partial guesses |
| Normalization | Versioned transformations, stable identities, unit/scope checks, reversible deduplication and conflict retention | Preserve unknowns and conflicting observations for review |
| Review | Authorized decision, exact input revision, evidence/rights assessment and independent approval where required | Withhold ineligible or unreviewed projections |
| Release assembly | Immutable manifest, exact dependencies, hashes, notices, complete eligibility and negative validation | Fail closed before promotion; keep the previous eligible release visible |
| Consumer delivery | Contract negotiation, integrity checks, use scope, correction/revocation channel and receipts | Reject incompatible artifacts; display an accurate retained/offline state |
| Correction/withdrawal | Attributable event, affected record/field/release inventory and downstream invalidation | Stop affected publication and propagate removal/restriction without erasing audit history |

An existing release may only be retained when its rights and safety remain eligible. Availability must not justify continuing distribution after a rights revocation or security withdrawal.

## Environments and credentials

Define isolated development, test, staging and production boundaries before runtime deployment. Synthetic fixtures must be rejected by real publication paths. Real restricted material must not enter public tests or public Git history.

Use least-privilege identities for acquisition, review, release promotion and consumer delivery. Separate permission to retrieve a source from permission to approve its public use. Store credentials in an approved secret facility, rotate and revoke them through a tested process, and sanitize logs and artifact locators.

Contributor CI has no production credentials. Workflows use only approved GitHub-owned actions with immutable pins and minimal permissions. Any deploy environment, operator allowlist, budget or credential grant needs explicit configuration and readback; none is implied by a workflow file.

Coordinate publication channels with the existing shared-service authority in website `services/planner-api`. Frozen v1 GET requests remain authenticated. An anonymous artifact channel requires an explicitly accepted public-distribution contract, rights assessment and consumer enforcement; it must not silently weaken the API's authentication or imply support for build writes and evaluations.

## Scheduling, freshness and replay

Choose source-specific polling or event schedules after source permission, rate limits, cost and business needs are understood. Record their rationale. Do not introduce a universal TTL: accepted research distinguishes pinned facts from current-state observations.

Use deterministic ingestion identities, bounded retry with jitter, idempotency keys, durable checkpoints and replay manifests. Distinguish a source's effective change from a retrieval timestamp and from the pipeline's processing time. Replaying a historical source must retain its original scope and must not refresh a claim's access date artificially.

A policy/terms change may invalidate an operation or field even when the source bytes are unchanged. Re-evaluate affected uses and record the decision. Failed retrieval preserves the prior observation and its age; it does not prove the underlying product is unavailable or that the prior value is still current.

## Monitoring and budgets

The implementation should measure acquisition success/failure, rate-limit responses, queue age, processing latency, quarantine volume, schema drift, duplicate/conflict rates, unresolved reviews, rights decision gaps, release rejection reasons, consumer failures, correction propagation and resource spend. Metrics should carry source and revision context without leaking sensitive content.

Alert thresholds, escalation coverage, retention periods, cost ceilings, capacity targets and SLOs require named accountable roles and accepted decisions. Record proposed targets as proposals. Test alerts with synthetic failure injection before claiming operational coverage.

## Incident playbooks to implement

### Source rights or terms change

Identify the affected source, material, operation and decision revision. Pause new affected acquisition/publication. Trace claims, fields, projections, releases, caches and consumers. Obtain the required rights decision; propagate restriction, correction or withdrawal events and required notices. Verify consumer behavior and record the resolution. Do not roll back to a release containing the same revoked material.

### Erroneous claim or entity merge

Preserve the original observation and review history. Identify the incorrect transform, claim or identity decision and its affected releases. Issue a correction or reversible split with exact lineage, rerun impacted validation, obtain review and publish a new immutable revision. Notify through the accepted consumer correction channel and retain the superseded state as audit history.

### Malicious source content or parser failure

Isolate the acquisition job and quarantine the input. Prevent automatic retries from repeatedly executing the same harmful workload. Review network and credential exposure, rotate affected credentials when warranted, preserve sanitized forensic metadata and repair the parser/limit. Reprocess only after a reviewed fix and bounded regression test.

### Corrupt, incompatible or unauthorized release

Stop promotion/distribution of the affected artifact, identify exact hashes and consumers, and preserve the failure receipt. Revert a channel pointer only to an independently confirmed eligible release. If none exists, expose unavailability and correction state rather than serving an unqualified fallback. Test consumers' integrity and compatibility rejection behavior.

### Availability or dependency outage

Bound retries and queues, communicate the last successful observation and current data age, and preserve idempotent checkpoints. Apply approved degradation behavior. Recovery must reconcile unfinished work without duplicate publication or false freshness.

### Credentials or personal data exposure

Use the private reporting process in [SECURITY.md](../SECURITY.md). Restrict affected access, revoke exposed credentials where authorized, and coordinate removal and incident response through authorized owners. Do not reproduce sensitive content in public issues, logs or remediation evidence.

## Backup, recovery and retention

Define backup scope for source decisions, normalized records, provenance, review receipts, manifests, correction events and operational state. Protect confidentiality and integrity, document restore dependencies, and test restoration into an isolated environment with checks of exact identity and referential consistency.

Recovery point and recovery time objectives remain unapproved until capacity and consumer requirements are measured. Retention follows source rights and operational needs; preserving an audit receipt does not authorize retaining or redistributing restricted underlying content forever. Store metadata necessary for tombstones and accountability while respecting accepted removal requirements.

## Release readiness

A production candidate requires an eligible real source and bounded pilot, versioned contracts, verified review/rights gates, reproducible immutable artifacts, consumer acceptance, tested security and failure behavior, authorized operating access, measured capacity/cost evidence, accepted monitoring and recovery objectives, tested restoration/rollback, and incident/correction procedures.

Each gate needs a real artifact or receipt linked from the release record. Synthetic examples establish test coverage only. Repository creation, a passing plan validator, a successful CI run or a completed issue hierarchy does not establish operational readiness.
