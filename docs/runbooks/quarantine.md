# Synthetic quarantine and re-entry rehearsal

Refs [CP-07.02, issue #34](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/34). This is an **offline, partial** prototype, not an accepted quarantine service, operational runbook, source-use authorization or publication gate.

`src/quarantine` records a bounded, immutable tuple of synthetic attempts. Every attempt requires five explicitly supplied per-gate results (schema, identity, evidence, rights and policy). A result is marked `quarantined` with machine-readable failure causes and candidate next actions, or `needs_independent_review` if all five input results pass. **Neither state authorizes publication.** A previous `pass` cannot be reused on re-entry; each of the five gates must supply a fresh synthetic evaluation identity and correction revision must increase. This only checks supplied test metadata; it does not prove a gate was actually run or authorized. The caller is responsible for independent rights, evidence, reviewer and release verification.

`evaluate_batch` isolates malformed entries and reports a disposition for each valid candidate. It emits no publishable subset, promotion command or source data. One malformed entry cannot suppress other candidates' diagnostics. The quarantine schema is a **draft** wire representation, not a shared accepted contract, and a validated schema does not confer product or material rights.

The prototype has no source access, filesystem storage, network calls, timestamps, durable evidence, independent actor authentication, or recovery. It holds no source or personal material. Maximum 32 attempts per candidate and 128 items per call; in-memory immutability is not durable append-only storage or a protection against arbitrary code with process access. It cannot independently detect a forged historical tuple that remains internally consistent. The caller must separately store prior receipts in an authenticated audit chain and ensure decisions are bound to actual candidate/source revisions.

Run the offline tests from the repository root with the pinned validation environment:

```sh
python -m unittest discover -s tests -p test_quarantine.py -v
python -m unittest discover -s tests -v
```

**Still required to complete #34:** accepted reason taxonomy/action semantics and escalation ownership; real ingestion/admission and exact source-rights gate integrations; provenance and review receipts; resilient quarantine persistence and correction history; actionable UI/triage, concurrency, idempotency and batch handling; negative tests at supported producer/consumer boundaries; independent reviewers and accepted operational/consumer evidence. Keep the issue open. No synthetic result can complete those gates.
