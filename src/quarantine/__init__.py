"""Offline, synthetic-only quarantine dispositions; never publication authority.

All five independent gate results are required at each attempt. The gate
implementation and external evidence custody are deliberately not supplied.
"""
from dataclasses import dataclass
import re

GATES = ("schema", "identity", "evidence", "rights", "policy")
CAUSES = {
    "malformed": ("schema", "correct_and_retry"),
    "identity_ambiguous": ("identity", "resolve_identity"),
    "evidence_insufficient": ("evidence", "supply_evidence"),
    "rights_unknown": ("rights", "request_rights_review"),
    "policy_denied": ("policy", "request_policy_review"),
}
MAX_ATTEMPTS = 32
MAX_BATCH = 128
_SYNTHETIC = re.compile(r"urn:pya:synthetic:[a-z0-9][a-z0-9:._-]*\Z")


class QuarantineError(ValueError):
    """Malformed or untrustworthy local attempt metadata."""


@dataclass(frozen=True, slots=True)
class GateFinding:
    gate: str
    status: str  # pass, reject or unknown
    evaluation_id: str
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class Attempt:
    candidate_id: str
    revision: int
    number: int
    state: str  # quarantined or needs_independent_review; never released
    causes: tuple[str, ...]
    next_actions: tuple[str, ...]
    findings: tuple[GateFinding, ...]


def _synthetic(value):
    return type(value) is str and len(value) <= 256 and _SYNTHETIC.fullmatch(value) is not None


def _normalize(findings):
    if type(findings) is not tuple or len(findings) != len(GATES):
        raise QuarantineError("A fresh result from all five gates is required")
    by_gate = {}
    for finding in findings:
        if type(finding) is not GateFinding or finding.gate not in GATES or finding.gate in by_gate:
            raise QuarantineError("Unknown or duplicate gate")
        if (type(finding.gate) is not str or type(finding.status) is not str
                or (finding.cause is not None and type(finding.cause) is not str)):
            raise QuarantineError("Gate fields must use exact scalar types")
        if finding.status not in ("pass", "reject", "unknown") or not _synthetic(finding.evaluation_id):
            raise QuarantineError("Invalid gate result or synthetic evaluation identity")
        if finding.status == "pass":
            if finding.cause is not None:
                raise QuarantineError("Passing gate cannot supply a failure cause")
        elif finding.cause not in CAUSES or CAUSES[finding.cause][0] != finding.gate:
            raise QuarantineError("Failed/unknown gate requires matching cause")
        by_gate[finding.gate] = finding
    ordered = tuple(by_gate[g] for g in GATES)
    if len({f.evaluation_id for f in ordered}) != len(GATES):
        raise QuarantineError("Gate evaluations must have distinct identities")
    return ordered


def _derived(findings):
    causes = tuple(f.cause for f in findings if f.cause is not None)
    actions = tuple(dict.fromkeys(CAUSES[c][1] for c in causes))
    return ("quarantined" if causes else "needs_independent_review", causes, actions)


def append_attempt(history, *, candidate_id, revision, findings):
    """Return a new immutable history; require new revision and all fresh gates.

    Data-only synthetic harness. An evaluation ID is not a signed receipt, and
    needs_independent_review is not permission to publish or release.
    """
    if not _synthetic(candidate_id) or type(revision) is not int or revision < 1:
        raise QuarantineError("Candidate and positive revision must be synthetic and exact")
    if type(history) is not tuple or len(history) >= MAX_ATTEMPTS:
        raise QuarantineError("History must be a bounded immutable tuple")
    seen = set()
    prior_revision = 0
    for number, entry in enumerate(history, 1):
        if type(entry) is not Attempt or entry.candidate_id != candidate_id:
            raise QuarantineError("Foreign or malformed prior attempt")
        if type(entry.number) is not int or entry.number != number or type(entry.revision) is not int or entry.revision <= prior_revision:
            raise QuarantineError("Nonmonotonic prior attempt history")
        normalized = _normalize(entry.findings)
        if normalized != entry.findings or (entry.state, entry.causes, entry.next_actions) != _derived(normalized):
            raise QuarantineError("Inconsistent prior attempt metadata")
        for finding in normalized:
            if finding.evaluation_id in seen:
                raise QuarantineError("Reused evaluation identity in prior history")
            seen.add(finding.evaluation_id)
        prior_revision = entry.revision
    if revision <= prior_revision:
        raise QuarantineError("Correction must use a strictly newer revision")
    normalized = _normalize(findings)
    if any(f.evaluation_id in seen for f in normalized):
        raise QuarantineError("Re-entry must supply new results from every gate")
    state, causes, actions = _derived(normalized)
    return history + (Attempt(candidate_id, revision, len(history) + 1,
                              state, causes, actions, normalized),)


def as_document(entry):
    """Machine-readable disposition, never an eligibility or rights receipt."""
    if type(entry) is not Attempt:
        raise QuarantineError("Expected an attempt")
    return {
        "synthetic": True, "candidate_id": entry.candidate_id,
        "revision": entry.revision, "attempt": entry.number,
        "state": entry.state, "causes": list(entry.causes),
        "next_actions": list(entry.next_actions),
        "evaluations": [dict(gate=f.gate, status=f.status,
                             evaluation_id=f.evaluation_id,
                             **({"cause": f.cause} if f.cause else {}))
                        for f in entry.findings],
    }


def evaluate_batch(items):
    """Return per-item (candidate_id, history, error), never publication output.

    Malformed entries are isolated so one bad packet cannot mask diagnostics for
    independent candidates. Duplicate candidate IDs fail closed in the batch.
    """
    if type(items) is not tuple or len(items) > MAX_BATCH:
        raise QuarantineError("Expected a bounded tuple of candidate inputs")
    used = set()
    results = []
    for item in items:
        if type(item) is not tuple or len(item) != 4:
            results.append((None, None, "malformed_batch_item"))
            continue
        candidate_id, revision, history, findings = item
        if not _synthetic(candidate_id):
            results.append((None, None, "invalid_candidate_id"))
        elif candidate_id in used:
            results.append((candidate_id, None, "duplicate_candidate_id"))
        else:
            used.add(candidate_id)
            try:
                results.append((candidate_id, append_attempt(
                    history, candidate_id=candidate_id, revision=revision,
                    findings=findings), None))
            except QuarantineError:
                results.append((candidate_id, None, "invalid_attempt"))
    return tuple(results)
