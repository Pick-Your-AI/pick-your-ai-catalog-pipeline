# Offline durable job/replay proposal

Refs #21 / CP-04.04. This is a bounded synthetic SQLite experiment, not an
accepted storage architecture, live connector, rights service, or production
recovery guarantee. CP-04.01 and CP-14.01 outcomes, affected-owner review,
independent review and operational acceptance remain prerequisites.

`src.jobs.ledger.JobLedger` uses only standard-library SQLite and test-created
temporary files. It accepts synthetic acquisition envelopes through the existing
`src.policy.acquisition.preflight` helper. No request, decision, source body,
parsed field value, URL, arbitrary exception text or credential is persisted.
The existing `synthetic_memory` retention condition does **not** authorize disk
retention of source content. The ledger persists only synthetic identifiers,
policy/request/result digests, fixed failure codes, counters and cursor tokens.
A digest proves identity only; none of these outputs establishes real rights.

## Replay procedure

1. Open a temporary database with an explicit mapping of 1–16 reserved synthetic
   source IDs to lifetime attempt budgets of 1–100. Reopen with the exact same
   mapping; changes are refused. There is no implicit reset window or quota refill.
2. `admit(run_id, request, decision, parser_version, now=...)` binds run, source,
   exact request and parser identities. A repeated run/request ID with different
   bytes, parser or decision is refused. Missing/denied valid policy creates a
   retained dead letter. Malformed API input raises a fixed `JobError`.
   An identical admission is a new call-time policy evaluation and advances the
   durable clock, including after reopen. As an explicit consistency rule, a
   newly evaluated refusal also dead-letters an existing `ready` or `retry` job;
   it cannot remain runnable merely because its identity was already admitted.
   A completed job retains its state, observations, checkpoint, quotas and prior
   receipts, with a separate refusal receipt. Dead/cancelled jobs remain unchanged
   and cannot be reopened by admission. Equal-time duplicates are allowed; they
   consume no attempts or quotas and do not duplicate an existing receipt. A
   permitted duplicate does not append another admission receipt or reset work.
3. `next_ready(now=...)` returns the oldest ready job from the least recently
   served eligible source. `attempt(job_id, request, current_decision, now=...)`
   rechecks current rights and the original decision digest under a write
   transaction. Supply the current synthetic decision again after reopen; an old
   stored grant cannot authorize replay. Changed, missing, malformed, expired,
   conditional or revoked decisions refuse further processing. The caller is
   responsible for obtaining current policy; there is no authority lookup here.
4. Supply `outcome="accepted"`, up to 32 exact `{id, digest}` observation
   descriptors, and an optional reserved synthetic checkpoint ID. The transaction
   commits descriptors, job links, checkpoint, quota charges, state and receipt
   together. Observation keys bind source, exact request, parser and logical ID,
   so repeated runs share an unchanged observation. Conflicting digests dead
   letter the new job without changing the previous observation.
5. `timeout`, `unavailable` and `rate_limited` are retryable simulated outcomes.
   Integer `retry_after` seconds (0–3600, with a minimum delay of one second)
   backpressure the entire source. Other sources remain schedulable. Each
   attempted outcome consumes both source and decision-ID/revision budgets.
   Eight attempts exhaust a job; `parse_failed` and `validation_failed` are
   permanent. Invalid API shapes do not constitute a simulated attempt; explicitly
   report a validated parser refusal as one of the permanent outcomes.
6. `cancel(job_id, now=...)` stops pending work. `snapshot(job_id)` returns bounded
   metadata and retained receipts with reason, attempt and synthetic clock time.
   Dead/cancelled jobs are terminal. Completed exact replay rechecks rights and
   returns without another quota charge or duplicate observation; conflicting or
   rights-refused replay records a refusal while retaining completed history.

Request, decision, observation and source-budget containers are detached into
bounded built-in primitives before semantic validation, hashing or SQLite waits.
Only that private snapshot is used through commit: mutating a caller's list or
nested dictionaries during lock contention cannot change persisted identities,
digests or quotas. Capture itself limits depth, nodes, container sizes, strings
and integers, and rejects unsupported objects without invoking copy hooks. A
malformed policy still retains the existing fixed refusal receipt; invalid result
shapes consume no work. Initialization failures close the SQLite connection.

This is call-time synthetic policy admission, not a revocation subscription.
Mutating a supplied dictionary does not update an in-flight call's policy;
explicitly supply the current decision on each new call, including completed
replay. Callers must synchronize changes during input capture if they require an
atomic view across multiple caller-owned containers. No authenticated authority
lookup or trusted live revocation mechanism is introduced.

`now` is a caller-supplied UTC instant, checked against a persistent nondecreasing
clock. This supports deterministic fixtures and is not a trusted time service.
All SQL mutations use `BEGIN IMMEDIATE`; exceptions roll back the transaction.
Snapshots read job, observation and receipt state in one deferred read transaction,
so another connection cannot expose mixed pre-commit and post-commit fields.
Read/query/commit failures release the transaction and preserve the SQLite error.
The concurrency regression enables WAL only on its temporary test database to
allow an interleaved writer commit; the implementation makes no journal-mode
change. Under default rollback journaling, a synchronous writer blocked by the
reader surfaces its normal lock timeout, rolls back and can be retried.
The ledger admits at most 100 jobs and provides no delete/reset API: use another
temporary database for a new experiment, retaining the old test receipts when
needed. No raw result data is recoverable from a checkpoint.

## Verification and limitations

Run `python -m unittest discover -s tests -p test_durable_jobs.py -v`.
Tests use temporary files, simulated outcomes, SQL abort injection and separate
local processes exiting before and after commit. They check rollback/reopen,
identical replay, conflicting identities/results, rights changes, quotas,
backpressure, source fairness, cancellation and retained dead letters. Separate
connections also hold real writer locks while caller-owned inputs change, checking
that descriptor counts, completion replay, policy bindings and budgets stay tied
to the admitted snapshot.
`schemas/ingestion-run.schema.json` describes the proposal's snapshots; it is
validated directly by these tests and is not registered as an accepted shared
contract. It changes no existing connector API, frozen contract or publication
gate. `done` means an atomic synthetic metadata admission, not a reviewed claim.

Power loss, disk corruption, backup/restore, multi-host workers, real transport
leases, authenticated policy custody, production retention, operational rate
windows, migration and live source/consumer acceptance are outside this proposal.
Passing local tests does not satisfy full issue acceptance or authorize rollout.
