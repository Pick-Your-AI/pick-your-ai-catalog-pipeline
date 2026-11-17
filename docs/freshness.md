# Freshness policy — proposed synthetic offline slice (CP-11.01, #53)

This is an **unaccepted draft**, not a catalog-wide TTL, data-source access decision, live scheduler, or publisher. The proposed contract (schemas/freshness-policy.schema.json) and evaluator (src/freshness/) accept **only synthetic receipts** under explicit source-specific policies. Successful evaluation never makes a claim true, rights-cleared, current in real time, independently reviewed, or publication-eligible. Frozen builder v1 is unchanged.

## Semantics

- **Pinned:** version_pinned_fact, immutable_release, historical_evidence never age out because a new catalog snapshot appears or a fixed number of seconds pass. Preserve the exact pinned revision. source_corrected always creates event_review for these claim types, even when event_triggers is empty or lists only other events; a simultaneous rights/source-policy event takes priority as rights_hold. Both results preserve the original observation and snapshot references for review without mutating history.
- **Current:** current_price, current_availability, current_offering require a proposed source-specific interval and/or explicitly named events. An interval measures time since checked_at, **not** capture, publication or effective dates. checked_as_of describes only a last check, not real-time truth. Event-only policies return as_of_only, not an indefinite assertion of currency.
- **Times:** captured_at records observation, checked_at a subsequent check, effective_at a source-asserted effective time (possibly future), and published_at catalog publication. All supplied fields remain distinct. Timestamps require explicit UTC Z strings with either whole seconds or one to six fractional digits. Greater precision is rejected for every timestamp, including effective_at, rather than truncated or rounded. A missing check is unchecked, never an invented date or an expiry of a pinned fact. Invalid/future capture/check/publication and checks before capture fail closed. Equality with the evaluation time is allowed; a future effective time is held. A current claim becomes review_due exactly at its declared interval after checked_at, with comparisons preserving microsecond precision.
- **Availability and rights:** unavailable/unknown source status preserves last-known evidence and requests escalation, never deletion. rights_changed or source_policy_changed puts even pinned claims on rights_hold pending an exact material/use decision. No operation fetches, sends, or republishes anything.
- **Events and snapshots:** declared source-specific triggers produce event_review, in addition to the unconditional pinned source-correction and rights/source-policy rules above. snapshot_created alone never invalidates old pinned facts, saved builds, or their artifact IDs. Unknown event types fail closed.

## Offline fixture verification

Run from the repository root with requirements-validation.txt installed:

    python -m unittest discover -s tests -p 'test_freshness.py' -v

All tests use fictional urn:pya:synthetic identities, explicit UTC Z timestamps and an illustrative 3,600-second price review rule. This is **not a validated real-source interval or universal freshness standard**. Every evaluation returns synthetic=true, publication_eligible=false, policy_id, status, next_action, and original timestamps and references.

The standalone evaluator is deliberately **not connected** to production acquisition, published channels, consumer delivery, builder state or rights authority. It cannot verify source truth, check authenticity, source-event identity, snapshot integrity, custody, review authority, or source permission. #53 remains open pending accepted provenance (#28), contract handoff (#9), exact source-specific policy rationale, source/consumer receipts and eligible independent GitHub approval. This draft is not a release or a source-rights grant.
