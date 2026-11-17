# Source reconciliation and outage (offline draft)

This runbook documents a **synthetic-only** scan assessor for CP-11.03 (#55). `src/reconciliation/assess_scan()` accepts explicit fictitious cursor pages; it performs no requests, scheduling, retries, persistence, rights checks, publication, deletion or notifications. All outputs are marked `synthetic=true` and `publication_eligible=false`. No source is approved or live. The current predecessor gates are #53 (source-specific freshness policy) and #21 (durable, rights-aware jobs/checkpoints).

## Offline exercise

Run `python -m unittest discover -s tests/reconciliation -v` from the repository root. Test cases exercise complete and incremental windows, missing cursor edges, cycles, broken links, parser/transport failures, quota pauses, explicit retry escalation, unexpected counts, and failed comparisons. The model deliberately separates an observation-window endpoint from authoritative source completeness. Every synthetic cursor/record is a reserved `urn:pya:synthetic:` identity; only bounded, strictly typed fixture data is accepted.

## Outage response boundary

1. Freeze any claim that a scan is complete when a cursor is missing or a page fails. Preserve last-known claims with their exact capture/check timestamps, source and rights context. **Not observed** is not **deleted**, **withdrawn** or **unpublished**.
2. Preserve the returned `resume_cursor` as an *uncommitted proposal*. A real runner must atomically persist source, permission revision, parser version, observation revision, acknowledged page and next cursor; replay must re-check current rights and source quotas first. The assessor makes no such guarantees.
3. On quota pause, wait for a verified source reset rather than retry immediately. For parse, link and transport failures, apply only an approved per-source budget; escalate when exhausted. Never infer source disappearance from failed reads. Rights changes preempt all retries.
4. Review count changes only against an explicitly comparable prior complete full run. A count change creates a human investigation request, not a tombstone. `compare_window()` is only a synthetic full-versus-rehydrated-incremental comparison for the *same declared source/window*; a match does not prove source completeness.
5. Before any production integration, obtain accepted source policy and permissions, checkpoint idempotency/recovery proof, independent reviewer approval, exact source-health metrics, operator runbooks and receiving-owner acceptance. A green fixture test cannot substitute for them.

No universal retry budget, freshness TTL, coverage denominator, SLO, external notification endpoint or source error interpretation is approved by this draft. All numerical fixture limits are defensive test bounds, not service commitments.
